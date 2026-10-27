namespace XinBotPet;

/// <summary>
/// 命令行入口。
///
/// 由 `xinbot start pet` 拉起，参数全部显式传入（不走配置文件）：
///   位置与尺寸由 Python 侧的多显示器/DPI 逻辑算好后交过来，
///   C# 只负责显示与窗口交互，避免两边各算一套。
///
/// 退出码：
///   0  正常关闭
///   2  参数错误
///   3  缺少 WebView2 运行时
/// </summary>
internal static class Program
{
    // DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
    private static readonly IntPtr PerMonitorAwareV2 = new(-4);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);

    [STAThread]
    private static int Main(string[] args)
    {
        // 崩溃排查用：WinExe 没有控制台，异常默认只弹一个看不见消息的框。
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
            Log("未处理异常: " + e.ExceptionObject);
        Application.ThreadException += (_, e) => Log("UI 线程异常: " + e.Exception);

        // 必须在创建任何窗口之前设置线程 DPI 上下文。
        // 只调 Application.SetHighDpiMode 不够：实测坐标仍被按 96→144 折算
        // （请求 480x630 得到 320x420，正好乘了 96/144），
        // 说明线程上下文仍是 96 DPI。
        try
        {
            SetThreadDpiAwarenessContext(PerMonitorAwareV2);
            Log("线程 DPI 上下文: PerMonitorV2");
        }
        catch (Exception error)
        {
            Log("设置线程 DPI 上下文失败: " + error.Message);
        }

        var options = Options.Parse(args);
        if (options is null || options.Help)
        {
            Console.Error.WriteLine(
                "用法: XinBotPet --url <地址> --x <int> --y <int> --width <int> --height <int> " +
                "[--state <文件>] [--no-passthrough] [--no-topmost]");
            return options is null ? 2 : 0;
        }

        if (!IsWebView2Available())
        {
            Console.Error.WriteLine(
                "缺少 Microsoft Edge WebView2 运行时。请安装后重试：\n" +
                "https://developer.microsoft.com/microsoft-edge/webview2/");
            return 3;
        }

        // 显式声明 DPI 感知：否则 Windows 会虚拟化坐标（实测 1000 变成 667），
        // 与 Python 侧按物理像素计算的位置对不上。
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        ApplicationConfiguration.Initialize();
        Application.Run(new PetWindow(
            options.Url!, options.StatePath ?? "", options.X, options.Y,
            options.Width, options.Height,
            clickThrough: !options.NoPassthrough, topMost: !options.NoTopmost,
            transparent: !options.NoTransparency));
        return 0;
    }

    private static bool IsWebView2Available()
    {
        try
        {
            string? version = Microsoft.Web.WebView2.Core.CoreWebView2Environment
                .GetAvailableBrowserVersionString();
            return !string.IsNullOrEmpty(version);
        }
        catch
        {
            return false;
        }
    }

    /// <summary>把诊断信息写到 %LOCALAPPDATA%\XinBot\pet-host.log。</summary>
    internal static void Log(string message)
    {
        try
        {
            string dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "XinBot");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "pet-host.log"),
                $"{DateTime.Now:HH:mm:ss.fff} {message}{Environment.NewLine}");
        }
        catch
        {
            // 日志失败不影响运行
        }
    }
}

internal sealed class Options
{
    public string? Url { get; private set; }
    public string? StatePath { get; private set; }
    public int X { get; private set; }
    public int Y { get; private set; }
    public int Width { get; private set; } = 320;
    public int Height { get; private set; } = 420;
    public bool NoPassthrough { get; private set; }
    public bool NoTopmost { get; private set; }
    public bool NoTransparency { get; private set; }
    public bool Help { get; private set; }

    public static Options? Parse(string[] args)
    {
        var options = new Options();
        for (int i = 0; i < args.Length; i++)
        {
            string key = args[i];
            switch (key)
            {
                case "--help" or "-h":
                    options.Help = true;
                    break;
                case "--url":
                    if (++i >= args.Length) return null;
                    options.Url = args[i];
                    break;
                case "--state":
                    if (++i >= args.Length) return null;
                    options.StatePath = args[i];
                    break;
                case "--x":
                    if (++i >= args.Length || !int.TryParse(args[i], out int x)) return null;
                    options.X = x;
                    break;
                case "--y":
                    if (++i >= args.Length || !int.TryParse(args[i], out int y)) return null;
                    options.Y = y;
                    break;
                case "--width":
                    if (++i >= args.Length || !int.TryParse(args[i], out int w)) return null;
                    options.Width = Math.Max(80, w);
                    break;
                case "--height":
                    if (++i >= args.Length || !int.TryParse(args[i], out int h)) return null;
                    options.Height = Math.Max(80, h);
                    break;
                case "--no-passthrough":
                    options.NoPassthrough = true;
                    break;
                case "--no-topmost":
                    options.NoTopmost = true;
                    break;
                case "--no-transparency":
                    options.NoTransparency = true;
                    break;
                default:
                    Console.Error.WriteLine($"未知参数: {key}");
                    return null;
            }
        }

        if (string.IsNullOrWhiteSpace(options.Url))
        {
            Console.Error.WriteLine("缺少 --url");
            return null;
        }
        return options;
    }
}
