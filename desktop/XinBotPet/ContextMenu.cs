using System.Runtime.InteropServices;

namespace XinBotPet;

/// <summary>
/// 右键菜单（Win32 原生 popup）。
///
/// 为什么不用网页里的 HTML 菜单：
/// 桌宠窗口是穿透的，页面收不到右键；而且菜单需要覆盖在窗口之外（可以超出窗口
/// 范围），HTML 菜单做不到。原生菜单还自带系统的键盘导航与主题。
/// </summary>
internal static class ContextMenu
{
    private const uint MF_STRING = 0x00000000;
    private const uint MF_SEPARATOR = 0x00000800;
    private const uint MF_CHECKED = 0x00000008;
    private const uint MF_UNCHECKED = 0x00000000;

    private const uint TPM_RETURNCMD = 0x0100;
    private const uint TPM_RIGHTBUTTON = 0x0002;
    private const uint TPM_NONOTIFY = 0x0080;

    public const int CMD_TOPMOST = 1;
    public const int CMD_CLICK_THROUGH = 2;
    public const int CMD_OPEN_WEB = 3;
    public const int CMD_TOGGLE_VISIBLE = 4;
    public const int CMD_QUIT = 5;

    [DllImport("user32.dll")]
    private static extern IntPtr CreatePopupMenu();

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool AppendMenuW(IntPtr menu, uint flags, int id, string text);

    [DllImport("user32.dll")]
    private static extern bool DestroyMenu(IntPtr menu);

    [DllImport("user32.dll")]
    private static extern int TrackPopupMenu(IntPtr menu, uint flags, int x, int y,
                                            int reserved, IntPtr hwnd, IntPtr rect);

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern bool PostMessageW(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam);

    private const int WM_NULL = 0x0000;

    /// <summary>
    /// 弹出菜单并返回用户选择（0 表示取消）。
    ///
    /// `SetForegroundWindow` + 事后 `PostMessage(WM_NULL)` 是 Win32 的老规矩：
    /// 不做的话菜单在点击别处时不会关闭。
    /// </summary>
    public static int Show(IntPtr hwnd, int x, int y,
                           bool alwaysOnTop, bool clickThrough, bool visible)
    {
        IntPtr menu = CreatePopupMenu();
        if (menu == IntPtr.Zero) return 0;

        try
        {
            AppendMenuW(menu, MF_STRING | (alwaysOnTop ? MF_CHECKED : MF_UNCHECKED),
                CMD_TOPMOST, "始终置顶");
            AppendMenuW(menu, MF_STRING | (clickThrough ? MF_CHECKED : MF_UNCHECKED),
                CMD_CLICK_THROUGH, "鼠标穿透");
            AppendMenuW(menu, MF_SEPARATOR, 0, string.Empty);
            AppendMenuW(menu, MF_STRING, CMD_OPEN_WEB, "打开完整界面");
            AppendMenuW(menu, MF_STRING, CMD_TOGGLE_VISIBLE, visible ? "隐藏桌宠" : "显示桌宠");
            AppendMenuW(menu, MF_SEPARATOR, 0, string.Empty);
            AppendMenuW(menu, MF_STRING, CMD_QUIT, "退出");

            SetForegroundWindow(hwnd);
            int choice = TrackPopupMenu(menu,
                TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY, x, y, 0, hwnd, IntPtr.Zero);
            PostMessageW(hwnd, WM_NULL, IntPtr.Zero, IntPtr.Zero);
            return choice;
        }
        finally
        {
            DestroyMenu(menu);
        }
    }
}
