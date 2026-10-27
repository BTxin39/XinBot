using System.Runtime.InteropServices;

namespace XinBotPet;

/// <summary>
/// DirectComposition + DWM 互操作。
///
/// 为什么非要走这条路：
/// WebView2 的 **HWND 宿主模式不支持分层窗口**——一旦给窗口加
/// `WS_EX_LAYERED`（无论色键还是 WinForms 的 TransparencyKey），
/// WebView2 就完全停止绘制。实测：不透明模式窗口内 281 种颜色，
/// 加上色键后只剩 1 种。
///
/// 官方支持逐像素透明的唯一方式是 **合成控制器**：
///   `CoreWebView2CompositionController` 把页面渲染进一个 DirectComposition
///   视觉（visual），再由 DWM 合成；窗口本身用
///   `DwmExtendFrameIntoClientArea(-1)` 让整块客户区参与逐像素 alpha。
///   这正是 Tauri 在 Windows 上的做法。
///
/// COM 注意事项：`[PreserveSig]` 方法必须**按 vtable 顺序**声明，
/// 跳过的方法也要留占位，否则调用会跑到别的方法上（直接崩）。
/// </summary>
internal static class Composition
{
    private const int S_OK = 0;

    [StructLayout(LayoutKind.Sequential)]
    public struct MARGINS
    {
        public int Left, Top, Right, Bottom;

        public static MARGINS Full => new() { Left = -1, Top = -1, Right = -1, Bottom = -1 };
    }

    [DllImport("dwmapi.dll")]
    private static extern int DwmExtendFrameIntoClientArea(IntPtr hwnd, ref MARGINS margins);

    [DllImport("dcomp.dll")]
    private static extern int DCompositionCreateDevice(
        IntPtr dxgiDevice, ref Guid iid, out IDCompositionDevice device);

    private static readonly Guid IID_IDCompositionDevice =
        new("C37EA93A-E7AA-450D-B16F-9746CB0407F3");

    /// <summary>让整块客户区参与逐像素 alpha（透出桌面）。</summary>
    public static void EnablePerPixelAlpha(IntPtr hwnd)
    {
        MARGINS margins = MARGINS.Full;
        DwmExtendFrameIntoClientArea(hwnd, ref margins);
    }

    /// <summary>创建 DirectComposition 设备并挂到窗口上，返回根 visual。</summary>
    public static object CreateRootVisual(IntPtr hwnd, out IDCompositionDevice? device)
    {
        device = null;
        Guid iid = IID_IDCompositionDevice;
        int hr = DCompositionCreateDevice(IntPtr.Zero, ref iid, out IDCompositionDevice created);
        Program.Log($"DCompositionCreateDevice hr=0x{hr:X8} created={created is not null}");
        if (hr != S_OK || created is null)
        {
            throw new InvalidOperationException($"DCompositionCreateDevice 失败: 0x{hr:X8}");
        }

        Program.Log("CreateTargetForHwnd...");
        int hrTarget = created.CreateTargetForHwndRaw(hwnd, true, out IntPtr targetPtr);
        Program.Log($"CreateTargetForHwnd hr=0x{hrTarget:X8} ptr=0x{targetPtr:X}");
        int hrVisual = created.CreateVisualRaw(out IntPtr visualPtr);
        Program.Log($"CreateVisual hr=0x{hrVisual:X8} ptr=0x{visualPtr:X}");
        if (hrTarget != 0 || targetPtr == IntPtr.Zero || hrVisual != 0 || visualPtr == IntPtr.Zero)
        {
            throw new InvalidOperationException($"DComp 创建失败: target=0x{hrTarget:X8} visual=0x{hrVisual:X8}");
        }
        // 为什么不用 `Marshal.GetObjectForIUnknown` + 强转 IDCompositionTarget：
        // 实测该 IID 的 QI 返回 E_NOINTERFACE（0x80004002），强转必失败。
        // 但对象本身有效、DComp 方法也都返回 S_OK。所以直接按 **vtable** 调
        // SetRoot，完全绕开 COM 接口封送（前 3 项是 IUnknown，SetRoot 是第 4 项）。
        CallSetRoot(targetPtr, visualPtr);
        created.Commit();
        Program.Log("DComp 已提交");

        device = created;
        // 只包成 IUnknown：WebView2 需要 IUnknown*，它自己会 QI 出 visual 接口。
        return Marshal.GetObjectForIUnknown(visualPtr);
    }

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int SetRootDelegate(IntPtr thisPtr, IntPtr visual);

    private static void CallSetRoot(IntPtr target, IntPtr visual)
    {
        IntPtr vtable = Marshal.ReadIntPtr(target);
        IntPtr slot = Marshal.ReadIntPtr(vtable, 3 * IntPtr.Size);
        var setRoot = Marshal.GetDelegateForFunctionPointer<SetRootDelegate>(slot);
        int hr = setRoot(target, visual);
        Program.Log($"SetRoot hr=0x{hr:X8}");
        if (hr != 0)
        {
            throw new InvalidOperationException($"SetRoot 失败: 0x{hr:X8}");
        }
    }
}

/// <summary>
/// IDCompositionDevice。
///
/// **只声明到 CreateVisual 为止，且顺序必须与 dcomp.h 一致**：
/// Commit → WaitForCommitCompletion → GetFrameStatistics → CreateTargetForHwnd → CreateVisual。
/// 少写中间的占位方法会导致调用落到错误槽位。
/// </summary>
[ComImport]
[Guid("C37EA93A-E7AA-450D-B16F-9746CB0407F3")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDCompositionDevice
{
    void Commit();
    void WaitForCommitCompletion();
    void GetFrameStatistics(IntPtr statistics);
    [PreserveSig]
    int CreateTargetForHwndRaw(IntPtr hwnd, [MarshalAs(UnmanagedType.Bool)] bool topmost,
                               out IntPtr target);
    [PreserveSig]
    int CreateVisualRaw(out IntPtr visual);
}

/// <summary>IDCompositionTarget：只用到 SetRoot（第一个方法）。</summary>
[ComImport]
[Guid("EACDD04C-117E-4E17-88F4-D1B12B0E4BD3")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDCompositionTarget
{
    void SetRoot(IDCompositionVisual visual);
}

/// <summary>
/// IDCompositionVisual。
///
/// 我们自己不调用它的任何方法——只是作为 `RootVisualTarget` 交给 WebView2，
/// 由 WebView2 把页面渲染进去。所以这里不需要声明方法，
/// 但保留了 Guid 以便必要时强转。
/// </summary>
[ComImport]
[Guid("4D93059D-097B-4651-9A60-F0F25116E2F3")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDCompositionVisual
{
}
