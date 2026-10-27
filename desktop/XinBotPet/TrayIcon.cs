using System.Drawing;
using System.Runtime.InteropServices;

namespace XinBotPet;

/// <summary>
/// 系统托盘图标（直接调 `Shell_NotifyIcon`，不引第三方包）。
///
/// 为什么需要它：桌宠窗口是无边框 + 不占任务栏的，
/// 没有托盘的话用户**根本没有关闭入口**——只能去任务管理器结束进程。
/// </summary>
internal sealed class TrayIcon : IDisposable
{
    private const int NIM_ADD = 0x00000000;
    private const int NIM_MODIFY = 0x00000001;
    private const int NIM_DELETE = 0x00000002;

    private const int NIF_MESSAGE = 0x00000001;
    private const int NIF_ICON = 0x00000002;
    private const int NIF_TIP = 0x00000004;
    private const int NIF_SHOWTIP = 0x00000080;

    /// <summary>托盘图标的回调消息号。用 WM_APP + 1，避免撞系统消息。</summary>
    public const int WM_TRAY = 0x8000 + 1;

    private const int TRAY_ID = 1;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct NOTIFYICONDATA
    {
        public int cbSize;
        public IntPtr hWnd;
        public uint uID;
        public uint uFlags;
        public uint uCallbackMessage;
        public IntPtr hIcon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string szTip;
        public uint dwState;
        public uint dwStateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string szInfo;
        public uint uVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string szInfoTitle;
        public uint dwInfoFlags;
        public Guid guidItem;
        public IntPtr hBalloonIcon;
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern bool Shell_NotifyIconW(int message, ref NOTIFYICONDATA data);

    [DllImport("user32.dll")]
    private static extern bool DestroyIcon(IntPtr hIcon);

    private readonly IntPtr _hwnd;
    private readonly string _tooltip;
    private IntPtr _iconHandle;
    private bool _added;

    public TrayIcon(IntPtr hwnd, string tooltip)
    {
        _hwnd = hwnd;
        _tooltip = tooltip;
    }

    public bool Add()
    {
        if (_added) return true;
        _iconHandle = CreateIconHandle();
        var data = BuildData(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP);
        if (!Shell_NotifyIconW(NIM_ADD, ref data))
        {
            return false;
        }
        // 告诉系统用新版的提示行为（否则 tooltip 可能不显示）
        data.uVersion = 4;
        Shell_NotifyIconW(NIM_MODIFY, ref data);
        _added = true;
        return true;
    }

    public void SetTooltip(string text)
    {
        if (!_added) return;
        var data = BuildData(NIF_TIP | NIF_SHOWTIP);
        data.szTip = text.Length > 120 ? text[..120] : text;
        Shell_NotifyIconW(NIM_MODIFY, ref data);
    }

    private NOTIFYICONDATA BuildData(int flags) => new()
    {
        cbSize = Marshal.SizeOf<NOTIFYICONDATA>(),
        hWnd = _hwnd,
        uID = TRAY_ID,
        uFlags = (uint)flags,
        uCallbackMessage = WM_TRAY,
        hIcon = _iconHandle,
        szTip = _tooltip,
    };

    /// <summary>
    /// 运行时画一个图标（绿圆 + 白点），不依赖外部 .ico 文件：
    /// 少一个二进制资源，也避免打包时漏文件。
    /// </summary>
    private static IntPtr CreateIconHandle()
    {
        try
        {
            using var bitmap = new Bitmap(32, 32);
            using (var graphics = Graphics.FromImage(bitmap))
            {
                graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                graphics.Clear(Color.Transparent);
                using var brush = new SolidBrush(Color.FromArgb(46, 160, 67));
                graphics.FillEllipse(brush, 2, 2, 28, 28);
                using var white = new SolidBrush(Color.White);
                graphics.FillEllipse(white, 13, 12, 7, 7);
            }
            return bitmap.GetHicon();
        }
        catch
        {
            return IntPtr.Zero;
        }
    }

    public void Dispose()
    {
        if (_added)
        {
            var data = BuildData(0);
            Shell_NotifyIconW(NIM_DELETE, ref data);
            _added = false;
        }
        if (_iconHandle != IntPtr.Zero)
        {
            DestroyIcon(_iconHandle);
            _iconHandle = IntPtr.Zero;
        }
    }
}
