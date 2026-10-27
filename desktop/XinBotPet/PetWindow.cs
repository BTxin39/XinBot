using System.Drawing;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;

namespace XinBotPet;

/// <summary>
/// 桌宠窗口——**合成控制器版**（透明由 DirectComposition + DWM 提供）。
///
/// 与 HWND 宿主模式的关键区别：
///   * 不再往窗口上加 `WS_EX_LAYERED`（那会让 WebView2 停止绘制）；
///   * 用 `DwmExtendFrameIntoClientArea(-1)` 让整块客户区参与逐像素 alpha；
///   * 页面渲染进 DirectComposition 视觉，由 DWM 合成到桌面。
///
/// 两件必须自己做、WebView2 不会代劳的事：
///   1. **命中检测**：窗口整块透明，只有角色身上该收鼠标，其余区域要穿透。
///      角色包围盒由页面通过 `window.__xinbotPet.bounds()` 上报。
///   2. **输入转发**：合成控制器没有子窗口，收不到鼠标消息，
///      必须把坐标换算后喂给 `SendMouseInput`。
/// </summary>
internal sealed class PetWindow : Form
{
    private readonly string _url;
    private readonly string _statePath;
    private readonly bool _clickThrough;
    private bool _clickThroughField;
    private readonly bool _transparent;
    private readonly Rectangle _requested;
    private readonly System.Windows.Forms.Timer _hitTest = new() { Interval = 80 };

    private CoreWebView2CompositionController? _controller;
    private IDCompositionDevice? _device;
    private bool _interactive;
    private bool _ready;

    /// <summary>角色包围盒（物理像素，客户区坐标）。null 表示还没拿到。</summary>
    private Rectangle? _petBox;
    private bool _boundsPending;
    private DateTime _lastBoundsAt = DateTime.MinValue;

    private TrayIcon? _tray;
    private bool _visible = true;

    // 拖拽状态：按下记录起点，移动超过阈值才搬窗口
    private bool _pressed;
    private bool _dragging;
    private Point _pressCursor;
    private Point _dragOriginCursor;
    private Point _dragOriginWindow;

    public PetWindow(string url, string statePath, int x, int y, int width, int height,
                     bool clickThrough, bool topMost, bool transparent = true)
    {
        _url = url;
        _statePath = statePath;
        _clickThrough = clickThrough;
        _clickThroughField = clickThrough;
        _transparent = transparent;
        _requested = new Rectangle(x, y, width, height);

        // 关掉 WinForms 的自动缩放：我们按物理像素精确摆放窗口
        AutoScaleMode = AutoScaleMode.None;
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        StartPosition = FormStartPosition.Manual;
        Bounds = _requested;
        BackColor = Color.Black;
        TopMost = topMost;
        Text = "XinBot 桌宠";
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);

        _hitTest.Tick += OnHitTestTick;
        Load += OnLoaded;
        FormClosing += OnClosing;
    }

    private static void Log(string message) => Program.Log(message);

    private async void OnLoaded(object? sender, EventArgs e)
    {
        Log("OnLoaded 开始");
        IntPtr handle = Handle;
        Native.MakeFramelessToolWindow(handle);
        Native.SetWindowPos(handle,
            TopMost ? Native.HWND_TOPMOST : IntPtr.Zero,
            _requested.X, _requested.Y, _requested.Width, _requested.Height,
            Native.SWP_NOACTIVATE);
        Native.ShowWindow(handle, Native.SW_SHOWNOACTIVATE);

        try
        {
            if (_transparent)
            {
                Composition.EnablePerPixelAlpha(handle);
            }

            string dataDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "XinBot", "WebView2");
            Directory.CreateDirectory(dataDir);

            CoreWebView2Environment env = await CoreWebView2Environment.CreateAsync(null, dataDir);
            _controller = await env.CreateCoreWebView2CompositionControllerAsync(handle);

            if (_transparent)
            {
                _controller.DefaultBackgroundColor = Color.Transparent;
            }

            object visual = Composition.CreateRootVisual(handle, out _device);
            _controller.RootVisualTarget = visual;

            // Bounds 用 DIP（96 DPI 为基准）
            int dipWidth = (int)Math.Round(_requested.Width * 96.0 / DeviceDpi);
            int dipHeight = (int)Math.Round(_requested.Height * 96.0 / DeviceDpi);
            _controller.Bounds = new Rectangle(0, 0, Math.Max(1, dipWidth), Math.Max(1, dipHeight));
            _controller.IsVisible = true;

            // 设置 RootVisualTarget 之后必须再提交一次，否则视觉里永远是空的
            _device?.Commit();

            CoreWebView2 core = _controller.CoreWebView2;
            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Navigate(_url);
            _ready = true;

            if (_clickThroughField)
            {
                Native.SetClickThrough(handle, true);
            }
            _hitTest.Start();

            // 托盘：无边框窗口不占任务栏，没有它用户就没有关闭入口
            _tray = new TrayIcon(handle, "XinBot 桌宠");
            if (!_tray.Add())
            {
                Log("托盘创建失败（右键菜单仍可用）");
            }

            Log("初始化完成");
        }
        catch (Exception error)
        {
            // 只记日志，不弹模态框：模态框会卡住调用它的脚本/父子进程
            Log("初始化异常: " + error);
            Close();
        }
    }

    // ── 命中检测 ──────────────────────────────────────────────

    private void OnHitTestTick(object? sender, EventArgs e)
    {
        if (!_ready || _controller is null) return;

        RefreshPetBounds();

        // 拖拽中不做穿透切换，否则会丢掉后续鼠标消息
        if (_dragging) return;

        if (!Native.GetCursorPos(out Native.POINT cursor)) return;
        if (!Native.GetWindowRect(Handle, out Native.RECT rect)) return;

        bool inside = HitTest(cursor, rect);
        if (inside == _interactive) return;
        _interactive = inside;

        if (_clickThroughField)
        {
            Native.SetClickThrough(Handle, !inside);
        }
    }

    /// <summary>光标是否落在角色身上（含少量容差）。</summary>
    private bool HitTest(Native.POINT cursor, Native.RECT window)
    {
        if (_petBox is Rectangle pet)
        {
            var target = new Rectangle(
                window.Left + pet.X, window.Top + pet.Y, pet.Width, pet.Height);
            target.Inflate(8, 8);   // 边缘容差，不至于点不到
            return target.Contains(cursor.X, cursor.Y);
        }

        const int inset = 16;
        return cursor.X >= window.Left + inset && cursor.X < window.Right - inset
            && cursor.Y >= window.Top + inset && cursor.Y < window.Bottom - inset;
    }

    /// <summary>
    /// 异步向页面要角色包围盒（CSS 像素），换算成物理像素缓存。
    /// 每 400ms 最多一次，且不等待上一次返回——避免卡住 UI 线程。
    /// </summary>
    private async void RefreshPetBounds()
    {
        if (_boundsPending || _controller is null) return;
        if ((DateTime.Now - _lastBoundsAt).TotalMilliseconds < 400) return;

        _boundsPending = true;
        _lastBoundsAt = DateTime.Now;
        try
        {
            string json = await _controller.CoreWebView2.ExecuteScriptAsync(
                "JSON.stringify(window.__xinbotPet && window.__xinbotPet.bounds ? window.__xinbotPet.bounds() : null)");
            _petBox = ParseBounds(json);
        }
        catch
        {
            // 页面还没准备好，下一轮再试
        }
        finally
        {
            _boundsPending = false;
        }
    }

    private Rectangle? ParseBounds(string json)
    {
        if (string.IsNullOrWhiteSpace(json) || json == "null") return null;
        try
        {
            // ExecuteScriptAsync 返回的是"JSON 字符串再包一层引号"，
            // 形如 "\"{\\\"x\\\":1,...}\""，要先反序列化出字符串再解析。
            string payload = System.Text.Json.JsonSerializer.Deserialize<string>(json) ?? "";
            if (string.IsNullOrWhiteSpace(payload) || payload == "null") return null;

            using var document = System.Text.Json.JsonDocument.Parse(payload);
            var root = document.RootElement;
            if (root.ValueKind != System.Text.Json.JsonValueKind.Object) return null;

            double scale = DeviceDpi / 96.0;
            int x = (int)Math.Round(root.GetProperty("x").GetDouble() * scale);
            int y = (int)Math.Round(root.GetProperty("y").GetDouble() * scale);
            int w = (int)Math.Round(root.GetProperty("width").GetDouble() * scale);
            int h = (int)Math.Round(root.GetProperty("height").GetDouble() * scale);
            if (w <= 0 || h <= 0) return null;
            return new Rectangle(x, y, w, h);
        }
        catch
        {
            return null;
        }
    }

    // ── 输入转发与拖拽 ────────────────────────────────────────

    protected override void WndProc(ref Message m)
    {
        const int WM_MOUSEMOVE = 0x0200;
        const int WM_LBUTTONDOWN = 0x0201;
        const int WM_LBUTTONUP = 0x0202;
        const int WM_RBUTTONUP = 0x0205;

        // 托盘图标上的右键：弹同一套菜单
        if (m.Msg == TrayIcon.WM_TRAY && (long)m.LParam == 0x0205)
        {
            Native.GetCursorPos(out Native.POINT trayPoint);
            ShowMenu(trayPoint.X, trayPoint.Y);
            return;
        }
        if (m.Msg == WM_RBUTTONUP)
        {
            Native.GetCursorPos(out Native.POINT point);
            ShowMenu(point.X, point.Y);
            return;   // 不转发右键，避免页面的 contextmenu 与原生菜单打架
        }

        if (_ready && _controller is not null)
        {
            switch (m.Msg)
            {
                case WM_LBUTTONDOWN:
                    OnPress();
                    return;   // 由我们自己决定是拖拽还是点击
                case WM_MOUSEMOVE:
                    if (_pressed && TryStartDrag()) return;
                    ForwardMouse(m, CoreWebView2MouseEventKind.Move);
                    break;
                case WM_LBUTTONUP:
                {
                    bool wasDragging = _dragging;
                    EndDrag();
                    if (!wasDragging)
                    {
                        // 走完一次完整的"按下-抬起"，页面才能收到 click
                        ForwardMouse(m, CoreWebView2MouseEventKind.LeftButtonDown);
                        ForwardMouse(m, CoreWebView2MouseEventKind.LeftButtonUp);
                    }
                    return;
                }
                default:
                    break;
            }
        }

        base.WndProc(ref m);
    }

    /// <summary>
    /// 记录按下位置。**必须先确认光标真在窗口内**：
    /// 窗口默认穿透，理论上收不到外部点击；但穿透切换存在几十毫秒延迟，
    /// 期间可能收到"光标在别处"的按下消息，直接用会把窗口甩到屏幕外。
    /// </summary>
    private void OnPress()
    {
        if (!Native.GetCursorPos(out Native.POINT cursor)) return;
        if (!Native.GetWindowRect(Handle, out Native.RECT rect)) return;
        if (cursor.X < rect.Left || cursor.X >= rect.Right
            || cursor.Y < rect.Top || cursor.Y >= rect.Bottom)
        {
            _pressed = false;
            return;
        }
        _pressCursor = new Point(cursor.X, cursor.Y);
        _pressed = true;
        _dragging = false;
    }

    /// <summary>
    /// 移动超过阈值才开始搬窗口——把"点击"和"拖动"分开，
    /// 否则手抖一下点击就变成拖拽。开始拖拽后不再把鼠标转发给页面。
    /// </summary>
    private bool TryStartDrag()
    {
        if (!Native.GetCursorPos(out Native.POINT cursor)) return false;
        int dx = cursor.X - _pressCursor.X;
        int dy = cursor.Y - _pressCursor.Y;

        // 单次跳动过大说明坐标是过期的（例如穿透切换瞬间），忽略这次
        if (Math.Abs(dx) > 400 || Math.Abs(dy) > 400)
        {
            _pressCursor = new Point(cursor.X, cursor.Y);
            return false;
        }

        if (!_dragging)
        {
            if (Math.Abs(dx) < 6 && Math.Abs(dy) < 6) return false;
            _dragging = true;
            _dragOriginCursor = new Point(cursor.X, cursor.Y);
            Native.GetWindowRect(Handle, out Native.RECT rect);
            _dragOriginWindow = new Point(rect.Left, rect.Top);
            Log("开始拖拽窗口");
        }

        Native.SetWindowPos(Handle, IntPtr.Zero,
            _dragOriginWindow.X + (cursor.X - _dragOriginCursor.X),
            _dragOriginWindow.Y + (cursor.Y - _dragOriginCursor.Y),
            0, 0,
            Native.SWP_NOSIZE | Native.SWP_NOZORDER | Native.SWP_NOACTIVATE);
        return true;
    }

    private void EndDrag()
    {
        _pressed = false;
        if (_dragging)
        {
            _dragging = false;
            SaveState();
            Log("拖拽结束，已保存位置");
        }
    }

    private void ForwardMouse(Message m, CoreWebView2MouseEventKind kind)
    {
        int x = unchecked((short)(long)m.LParam);
        int y = unchecked((short)((long)m.LParam >> 16));
        try
        {
            _controller!.SendMouseInput(kind, CoreWebView2MouseEventVirtualKeys.None, 0, new Point(x, y));
        }
        catch
        {
            // 输入转发失败不该让桌宠崩掉
        }
    }

    private void ShowMenu(int x, int y)
    {
        int choice = ContextMenu.Show(Handle, x, y, TopMost, _clickThroughField, _visible);
        switch (choice)
        {
            case ContextMenu.CMD_TOPMOST:
                TopMost = !TopMost;
                Native.SetWindowPos(Handle,
                    TopMost ? Native.HWND_TOPMOST : IntPtr.Zero, 0, 0, 0, 0,
                    Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE);
                Log($"置顶切换: {TopMost}");
                break;
            case ContextMenu.CMD_CLICK_THROUGH:
                SetClickThroughEnabled(!_clickThroughField);
                Log($"穿透切换: {_clickThroughField}");
                break;
            case ContextMenu.CMD_OPEN_WEB:
                OpenWeb();
                break;
            case ContextMenu.CMD_TOGGLE_VISIBLE:
                ToggleVisible();
                break;
            case ContextMenu.CMD_QUIT:
                Close();
                break;
        }
    }

    /// <summary>切换穿透模式。关闭穿透后窗口会一直接收鼠标（便于调试）。</summary>
    private void SetClickThroughEnabled(bool enabled)
    {
        _clickThroughField = enabled;
        if (enabled)
        {
            Native.SetClickThrough(Handle, true);
            _interactive = false;
        }
        else
        {
            Native.SetClickThrough(Handle, false);
        }
    }

    private void OpenWeb()
    {
        try
        {
            string baseUrl = _url.Split("/#")[0];
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = baseUrl + "/#/",
                UseShellExecute = true,
            });
        }
        catch (Exception error)
        {
            Log("打开界面失败: " + error.Message);
        }
    }

    private void ToggleVisible()
    {
        _visible = !_visible;
        Native.ShowWindow(Handle, _visible ? Native.SW_SHOWNOACTIVATE : 0 /* SW_HIDE */);
        Log(_visible ? "显示桌宠" : "隐藏到托盘");
    }

    private void OnClosing(object? sender, FormClosingEventArgs e)
    {
        _hitTest.Stop();
        _tray?.Dispose();
        _tray = null;
        SaveState();
        try { _controller?.Close(); } catch { }
        _controller = null;
    }

    private void SaveState()
    {
        try
        {
            if (string.IsNullOrEmpty(_statePath)) return;
            if (!Native.GetWindowRect(Handle, out Native.RECT rect)) return;
            string json = $"{{\"x\":{rect.Left},\"y\":{rect.Top}," +
                          $"\"width\":{rect.Right - rect.Left},\"height\":{rect.Bottom - rect.Top}}}";
            File.WriteAllText(_statePath, json);
        }
        catch
        {
            // 保存失败不影响退出
        }
    }
}
