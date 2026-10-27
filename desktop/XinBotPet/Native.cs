using System.Runtime.InteropServices;

namespace XinBotPet;

/// <summary>
/// Win32 互操作。集中放这里，Program.cs 只调用语义化方法。
///
/// 只做四件事：分层/色键透明、置顶、工具窗、鼠标穿透，外加光标与窗口矩形查询。
/// </summary>
internal static class Native
{
    public const int GWL_EXSTYLE = -20;
    public const int GWL_STYLE = -16;

    public const int WS_CAPTION = 0x00C00000;
    public const int WS_THICKFRAME = 0x00040000;
    public const int WS_EX_LAYERED = 0x00080000;
    public const int WS_EX_TRANSPARENT = 0x00000020;
    public const int WS_EX_TOOLWINDOW = 0x00000080;
    public const int WS_EX_APPWINDOW = 0x00040000;

    public const int LWA_COLORKEY = 0x00000001;

    public const int SW_SHOWNOACTIVATE = 4;

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT
    {
        public int Left, Top, Right, Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct POINT
    {
        public int X, Y;
    }

    [DllImport("user32.dll", SetLastError = true)]
    public static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetLayeredWindowAttributes(IntPtr hwnd, uint crKey, byte bAlpha, uint dwFlags);

    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool GetCursorPos(out POINT lpPoint);

    [DllImport("user32.dll")]
    public static extern short GetAsyncKeyState(int vKey);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    public static readonly IntPtr HWND_TOPMOST = new(-1);
    public const uint SWP_NOSIZE = 0x0001;
    public const uint SWP_NOMOVE = 0x0002;
    public const uint SWP_NOACTIVATE = 0x0010;
    public const uint SWP_NOZORDER = 0x0004;

    public const int VK_LBUTTON = 0x01;

    /// <summary>COLORREF 是 0x00BBGGRR 顺序，别直接塞 RGB。</summary>
    public static uint ToColorRef(int r, int g, int b) => (uint)(b << 16 | g << 8 | r);

    /// <summary>
    /// 去掉标题栏/边框，并设为工具窗（不占任务栏、不参与 Alt+Tab）。
    ///
    /// **刻意不加 `WS_EX_LAYERED`**：WebView2 不支持分层窗口，一加就停止绘制。
    /// 透明由 DirectComposition + DWM 提供（见 Composition.cs），
    /// 鼠标穿透只用 `WS_EX_TRANSPARENT`（不需要 LAYERED）。
    /// </summary>
    public static void MakeFramelessToolWindow(IntPtr hwnd)
    {
        int style = GetWindowLong(hwnd, GWL_STYLE) & ~(WS_CAPTION | WS_THICKFRAME);
        SetWindowLong(hwnd, GWL_STYLE, style);

        int ex = GetWindowLong(hwnd, GWL_EXSTYLE);
        ex = (ex | WS_EX_TOOLWINDOW) & ~(WS_EX_APPWINDOW | WS_EX_LAYERED);
        SetWindowLong(hwnd, GWL_EXSTYLE, ex);
    }

    /// <summary>
    /// 把指定颜色设成透明键。
    ///
    /// 与 WinForms 的 `TransparencyKey` 的区别：后者靠**窗口区域裁剪**，
    /// 会把 WebView2 子窗口一起裁掉；`LWA_COLORKEY` 由 DWM 在**合成阶段**
    /// 逐像素判定，对子窗口渲染没有影响。
    /// </summary>
    public static bool SetColorKey(IntPtr hwnd, int r, int g, int b)
    {
        int ex = GetWindowLong(hwnd, GWL_EXSTYLE);
        SetWindowLong(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED);
        return SetLayeredWindowAttributes(hwnd, ToColorRef(r, g, b), 0, LWA_COLORKEY);
    }

    public static bool SetClickThrough(IntPtr hwnd, bool enabled)
    {
        int ex = GetWindowLong(hwnd, GWL_EXSTYLE);
        int updated = enabled ? ex | WS_EX_TRANSPARENT : ex & ~WS_EX_TRANSPARENT;
        // 不要顺手加 LAYERED：那会让 WebView2 停绘。
        SetWindowLong(hwnd, GWL_EXSTYLE, updated);
        // 读回实际状态，不假设设置成功
        return (GetWindowLong(hwnd, GWL_EXSTYLE) & WS_EX_TRANSPARENT) != 0;
    }

    public static bool IsClickThrough(IntPtr hwnd) =>
        (GetWindowLong(hwnd, GWL_EXSTYLE) & WS_EX_TRANSPARENT) != 0;
}
