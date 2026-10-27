"""桌面常驻桌宠外壳。

职责边界（重要）：
    本模块**只负责显示与窗口交互**。对话、记忆、角色全部走后端 HTTP/WS，
    不在本进程里创建 Agent —— 否则会出现两个进程各自持有 Agent、
    写同一个 SQLite 的竞态（v0.2.0 修过的 D4 问题）。

技术要点见 docs/DECISIONS/DECISIONS_v0.2.2.md §4.3：
    透明 = pywebview `transparent=True` + 窗体 `BackColor == TransparencyKey`；
    穿透 = 直接改 `WS_EX_TRANSPARENT`，命中检测在本进程轮询。
"""

from __future__ import annotations

import contextlib
import threading
import time
from pathlib import Path

from app.interfaces.desktop import csharp_host, geometry, settings, win32_api
from app.interfaces.desktop.geometry import Rect, hit_test

# 命中检测轮询间隔：50ms 足够跟手，又不会把 CPU 烧起来
POLL_SECONDS = 0.05
# 拖拽判定阈值：光标移动超过该距离才开始移动窗口（避免点击时抖动）
DRAG_THRESHOLD = 3
# 启动后持续兜底显示窗口的时长（覆盖 pywebview 透明 hack 的 Hide）
VISIBILITY_RETRY_SECONDS = 12.0
# 窗口标题：既用于显示，也用于按标题枚举 HWND（见 win32_api.find_window_by_title）
WINDOW_TITLE = "XinBot 桌宠"
# 透明键颜色。选纯洋红：动画素材里几乎不会出现这个精确值，
# 万一出现（会被抠成洞）可改这里。
MAGIC_COLOR = (255, 0, 255)
MAGIC_COLOR_HEX = "#FF00FF"


class PetShell:
    """桌宠窗口的生命周期管理与交互。"""

    def __init__(self, url: str, repo_root: Path, *, click_through: bool = True,
                 always_on_top: bool = True, with_tray: bool = True):
        self.url = url
        self.repo_root = Path(repo_root)
        self.with_tray = with_tray
        self.state = settings.load(self.repo_root)
        self.state.click_through = click_through
        self.state.always_on_top = always_on_top
        self._window = None
        self._hwnd = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._tray = None
        self._autostart = None
        self._content: Rect | None = None
        self._drag_origin: tuple[int, int] | None = None
        self._drag_window_origin: tuple[int, int] | None = None
        self._interactive = False
        self._last_error = ""
        self._dpi_mode = "unknown"

    # ── 对外接口 ───────────────────────────────────────────────

    def run(self) -> int:
        """启动窗口（阻塞直到用户关闭）。返回进程退出码。"""
        import webview

        # 必须先声明 DPI 感知，再取显示器/创建窗口：
        # 否则枚举到的是逻辑坐标、GetWindowRect 是物理坐标，两者混用会把窗口
        # 位置算到屏幕外（实测：工作区宽 1707，却存下 x=2107）。
        self._dpi_mode = win32_api.ensure_dpi_aware()

        # 坐标约定：状态存逻辑像素，窗口 API 收物理像素（DPI 感知进程下
        # pywebview 两者都按物理处理）。这里取**物理**显示器列表 + 目标屏 DPI，
        # 由 restore 内部换算，避免外面重复乘除。
        monitors = win32_api.monitors()
        target = geometry.find_monitor(monitors, self.state.monitor) or monitors[0]
        self._dpi = win32_api.dpi_for_monitor(target)

        rect = self.state.restore(monitors, dpi=self._dpi)
        self.state.dpi = float(self._dpi)

        # 记下窗口落在哪块屏，下次优先放回去
        host = geometry.monitor_at(monitors, rect.left + rect.width // 2,
                                   rect.top + rect.height // 2)
        if host is not None and host.name:
            self.state.monitor = host.name

        self._window = webview.create_window(
            WINDOW_TITLE,
            self.url,
            width=rect.width,
            height=rect.height,
            x=rect.left,
            y=rect.top,
            frameless=True,
            # 关键：**不用 pywebview 的 transparent=True**。
            # 它在 Windows 上走"先 Show 再 Hide，等 NavigationStarting 再显示"的
            # 分支，实测会让 WebView2 停止绘制：页面已加载、模型资源已请求，
            # 但窗口一片空白（与 transparent=False 的对照实验差 2101 种颜色）。
            # 透明改由我们自己从 Win32 施加（见 _transparent_key），确定性更好。
            transparent=False,
            background_color=MAGIC_COLOR_HEX,
            on_top=self.state.always_on_top,
            shadow=False,
            easy_drag=False,
            resizable=False,
        )
        # 让前端能主动上报角色包围盒（命中检测用）
        with contextlib.suppress(Exception):
            self._window.expose(self.report_bounds, self.hide_window, self.close_window)

        self._running = True
        # 注意：不要设 `private_mode=False`。
        # 那会让 WebView2 使用持久化 profile，若上一次进程留下锁，
        # WebView2 初始化会卡住 → 永不触发 NavigationStarting →
        # pywebview 的透明分支（先隐藏、导航时再显示）就永远不显示窗口。
        # P2 实测踩到：窗口存在、样式正确，但 IsWindowVisible 恒为 0。
        webview.start(self._on_ready, debug=False)
        self._running = False
        # 关窗时一并回收托盘与轮询线程，避免进程退不干净
        if self._tray is not None:
            self._tray.stop()
            self._tray = None
        # 窗口关闭后停止轮询线程
        if self._thread:
            self._thread.join(timeout=1.5)
        return 0

    def report_bounds(self, left, top, width, height) -> dict:
        """前端通过 `pywebview.api.report_bounds(...)` 上报角色画布相对窗口的位置。"""
        self._content = Rect(int(left), int(top), int(width), int(height))
        return {"ok": True}

    def hide_window(self) -> dict:
        self.state.visible = False
        settings.save(self.repo_root, self.state)
        if self._window is not None:
            self._window.hide()
        return {"ok": True}

    def close_window(self) -> dict:
        self.save_position()
        if self._window is not None:
            self._window.destroy()
        self._running = False
        return {"ok": True}

    def save_position(self) -> None:
        """把当前窗口位置存回状态（位置与尺寸都换算回逻辑像素）。

        `GetWindowRect` 给物理像素，状态存逻辑像素 + 当时的 DPI，
        这样换到不同缩放的显示器上，"观感大小"才不会突变。
        """
        rect = win32_api.window_rect(self._hwnd)
        if rect:
            scale = win32_api.dpi_for_rect(rect) or 1.0
            self.state.from_physical(rect, scale)
            monitors = win32_api.monitors()
            host = geometry.monitor_at(monitors, rect.left + rect.width // 2,
                                       rect.top + rect.height // 2)
            if host is not None and host.name:
                self.state.monitor = host.name
        settings.save(self.repo_root, self.state)

    # ── 内部 ──────────────────────────────────────────────────

    def _on_ready(self) -> None:
        """窗口创建完成后的初始化：施加窗口样式、启动托盘与交互轮询。"""
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._start_tray()

    # ── 托盘 ──────────────────────────────────────────────────

    def _start_tray(self) -> bool:
        """启动托盘图标。失败不影响桌宠本体（没有托盘也能用右键菜单）。"""
        if not self.with_tray:
            return False
        from app.interfaces.desktop import autostart as autostart_module
        from app.interfaces.desktop.tray import TrayIcon

        self._autostart = autostart_module.Autostart()
        self._tray = TrayIcon(self._on_tray_action)
        try:
            enabled = self._autostart.status() is not None
        except Exception:  # noqa: BLE001  读注册表失败不应拖垮启动
            enabled = False
        self._tray.update_state(
            topmost=self.state.always_on_top,
            click_through=self.state.click_through,
            autostart=enabled,
        )
        return self._tray.start()

    def _on_tray_action(self, key: str) -> None:
        """处理托盘菜单点击。所有动作都转成与右键菜单一致的行为。"""
        if key == "toggle_topmost":
            self.state.always_on_top = not self.state.always_on_top
            win32_api.set_topmost(self._hwnd, self.state.always_on_top)
            settings.save(self.repo_root, self.state)
            if self._tray:
                self._tray.update_state(topmost=self.state.always_on_top)
        elif key == "toggle_click_through":
            self.state.click_through = not self.state.click_through
            win32_api.set_click_through(self._hwnd, self.state.click_through)
            settings.save(self.repo_root, self.state)
            if self._tray:
                self._tray.update_state(click_through=self.state.click_through)
        elif key == "toggle_autostart":
            self._toggle_autostart()
        elif key == "open_web":
            self._open_browser()
        elif key == "toggle_visible":
            self._toggle_visible()
        elif key == "quit":
            self.close_window()

    def _toggle_autostart(self) -> bool:
        """切换开机自启，返回切换后的状态。"""
        from app.interfaces.desktop import autostart as autostart_module

        manager = getattr(self, "_autostart", None) or autostart_module.Autostart()
        self._autostart = manager
        try:
            if manager.status() is None:
                manager.enable(autostart_module.Autostart.default_command(self.repo_root))
                enabled = True
            else:
                manager.disable()
                enabled = False
        except Exception as error:  # noqa: BLE001
            self._last_error = f"切换开机自启失败：{error}"
            return False
        if self._tray:
            self._tray.update_state(autostart=enabled)
        return enabled

    def _toggle_visible(self) -> None:
        if self._window is None:
            return
        try:
            if self.state.visible:
                self._window.hide()
                self.state.visible = False
            else:
                self._window.show()
                win32_api.show_window(self._hwnd)
                self.state.visible = True
            settings.save(self.repo_root, self.state)
        except Exception as error:  # noqa: BLE001
            self._last_error = f"切换显示失败：{error}"

    def _transparent_key(self) -> None:
        """让窗口透明：窗体底色 = 魔法色，并由 DWM 在合成阶段抠掉该色。

        为什么不用 pywebview 的 `transparent=True`：
        它那条路径会让 WebView2 停止绘制（对照实验：`transparent=False` 时
        同一页面渲染出 2101 种颜色，`True` 时窗口全空）。
        这里用不透明窗口 + 自己的 `LWA_COLORKEY`，渲染与透明互不干扰。

        也不用 WinForms 的 `TransparencyKey`：它靠窗口区域裁剪，
        会把 WebView2 子窗口整块裁掉。
        """
        try:
            from System.Drawing import Color

            form = self._window.native
            form.BackColor = Color.FromArgb(255, *MAGIC_COLOR)
        except Exception as error:  # noqa: BLE001
            self._last_error = f"设置窗体底色失败：{error}"

        if not win32_api.set_color_key(self._hwnd, MAGIC_COLOR):
            self._last_error = "SetLayeredWindowAttributes(LWA_COLORKEY) 失败"

    def _locate(self) -> bool:
        """找到窗口句柄、施加样式并确保窗口可见；成功返回 True。

        两条路径，按可靠性排序：
          1. `window.native` —— 快，但依赖 pywebview 内部时序（可能拿到 0）；
          2. 按窗口标题枚举 —— 确定性，P0 spike 验证过。
        """
        if self._hwnd:
            return True

        hwnd = 0
        try:
            native = self._window.native
            if native is not None:
                hwnd = int(native.Handle.ToInt64())
        except Exception as error:  # noqa: BLE001
            self._last_error = f"读取 native 句柄失败：{error}"

        if not hwnd:
            hwnd = win32_api.find_window_by_title(WINDOW_TITLE, timeout=0.5)
        if not hwnd:
            return False

        self._hwnd = hwnd
        win32_api.make_frameless_toolwindow(hwnd)
        win32_api.set_topmost(hwnd, self.state.always_on_top)
        self._transparent_key()

        # pywebview 的透明 hack 会先 Show 再 Hide，等 NavigationStarting 再显示。
        # 若那次导航没发生或发生在我们的调用之前，窗口会一直隐藏。
        try:
            self._window.show()
        except Exception as error:  # noqa: BLE001
            self._last_error = f"window.show() 失败：{error}"
        win32_api.show_window(hwnd)
        return True

    def _loop(self) -> None:
        """交互轮询：命中检测 + 鼠标穿透切换 + 拖拽 + 位置保存。"""
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and not self._locate():
            time.sleep(0.1)

        # 默认先穿透，避免启动瞬间挡住桌面
        if self._hwnd and self.state.click_through:
            win32_api.set_click_through(self._hwnd, True)

        # pywebview 在透明模式下会先 Show 再 Hide（等 NavigationStarting 再显示）。
        # 这个 hack 可能发生在我们的显示调用**之后**，导致窗口一直隐藏：
        # P2 实测页面已正常加载、窗口样式全对，但 IsWindowVisible 恒为 0。
        # 因此启动后的前若干秒内持续兜底显示。
        ensure_until = time.monotonic() + VISIBILITY_RETRY_SECONDS

        while self._running:
            try:
                if time.monotonic() < ensure_until and self._hwnd:
                    if not win32_api.is_visible(self._hwnd):
                        win32_api.show_window(self._hwnd)
                self._tick()
            except Exception as error:  # noqa: BLE001  轮询不能因单次异常退出
                self._last_error = f"交互轮询异常：{error}"
            time.sleep(POLL_SECONDS)

        self.save_position()

    def _tick(self) -> None:
        rect = win32_api.window_rect(self._hwnd)
        if rect is None:
            return

        cursor = win32_api.cursor_pos()
        inside = hit_test(cursor[0], cursor[1], rect, self._content)

        # 只有在"点到角色"时才取消穿透，其余时间让鼠标穿过窗口
        if inside != self._interactive:
            self._interactive = inside
            if self.state.click_through:
                win32_api.set_click_through(self._hwnd, not inside)

        if not inside:
            self._drag_origin = None
            return

        self._handle_drag(rect, cursor)
        self._handle_right_click()

    def _handle_drag(self, rect: Rect, cursor: tuple[int, int]) -> None:
        """按住左键拖动窗口。

        注意：不能用 GetAsyncKeyState 的上升沿做"开始拖拽"的唯一依据，
        因为点击也会触发；这里用位移阈值把"点击"和"拖动"区分开。
        """
        if win32_api.left_button_down():
            if self._drag_origin is None:
                self._drag_origin = cursor
                self._drag_window_origin = (rect.left, rect.top)
                return
            dx = cursor[0] - self._drag_origin[0]
            dy = cursor[1] - self._drag_origin[1]
            if abs(dx) >= DRAG_THRESHOLD or abs(dy) >= DRAG_THRESHOLD:
                origin = self._drag_window_origin or (rect.left, rect.top)
                win32_api.move_window(self._hwnd, origin[0] + dx, origin[1] + dy)
        elif self._drag_origin is not None:
            # 松手：保存位置
            self._drag_origin = None
            self._drag_window_origin = None
            self.save_position()

    def _handle_right_click(self) -> None:
        if win32_api.right_button_down():
            self._show_menu()

    def _show_menu(self) -> None:
        """右键菜单：用前端 HTML 菜单太重，这里直接用 Win32 原生菜单。"""
        import ctypes

        from app.interfaces.desktop import win32_api as api

        user32 = ctypes.windll.user32
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        items = [
            (1, "置顶：切换"),
            (2, "鼠标穿透：切换"),
            (3, "打开完整界面"),
            (4, "隐藏桌宠"),
            (5, "退出"),
        ]
        for index, (item_id, label) in enumerate(items):
            if item_id == 4:
                user32.AppendMenuW(menu, 0x00000000, 0, None)  # 分隔线
            user32.AppendMenuW(menu, 0x00000000, item_id, label)

        x, y = api.cursor_pos()
        # TPM_RETURNCMD | TPM_RIGHTBUTTON
        choice = user32.TrackPopupMenu(menu, 0x0100 | 0x0002, x, y, 0, self._hwnd, None)
        user32.DestroyMenu(menu)

        if choice == 1:
            self.state.always_on_top = not self.state.always_on_top
            api.set_topmost(self._hwnd, self.state.always_on_top)
            settings.save(self.repo_root, self.state)
        elif choice == 2:
            self.state.click_through = not self.state.click_through
            api.set_click_through(self._hwnd, self.state.click_through)
            settings.save(self.repo_root, self.state)
        elif choice == 3:
            self._open_browser()
        elif choice == 4:
            self.hide_window()
        elif choice == 5:
            self.close_window()

    def _open_browser(self) -> None:
        import webbrowser

        base = self.url.split("/#")[0]
        webbrowser.open(base + "/#/")


def run(url: str, repo_root: Path, *, click_through: bool = True,
        always_on_top: bool = True, with_tray: bool = True) -> int:
    """入口：启动桌宠窗口。

    优先用 **C# 宿主**（唯一能真正做到逐像素透明的实现），
    找不到时回退到 pywebview 版本（非透明，仅供开发调试）。
    """
    if not win32_api.available():
        raise RuntimeError("桌宠窗口目前仅支持 Windows。")

    root = Path(repo_root)
    host = csharp_host.find_host(root)
    if host is not None:
        return _run_csharp_host(host, url, root, click_through, always_on_top)

    # 回退：pywebview（透明不可用，见 DECISIONS v0.2.2 §26）
    try:
        import webview  # noqa: F401
    except ImportError as error:
        raise RuntimeError(
            "没有可用的桌宠宿主：既缺少 C# 宿主 XinBotPet.exe，"
            "也未安装 pywebview。请运行 scripts/build_desktop_shell.py 构建宿主。"
        ) from error

    return PetShell(
        url,
        root,
        click_through=click_through,
        always_on_top=always_on_top,
        with_tray=with_tray,
    ).run()


def _run_csharp_host(host: Path, url: str, root: Path,
                     click_through: bool, always_on_top: bool) -> int:
    """用 C# 宿主跑桌宠，并把退出时的窗口位置写回状态。"""
    state = settings.load(root)
    monitors = win32_api.monitors()
    target = geometry.find_monitor(monitors, state.monitor) or monitors[0]
    dpi = win32_api.dpi_for_monitor(target)
    rect = state.restore(monitors, dpi=dpi)
    state.dpi = float(dpi)

    rect_path = root / "data" / "_pet_rect.json"
    code, final = csharp_host.run(
        host, url, rect, rect_path,
        click_through=click_through, topmost=always_on_top,
    )

    if final is not None:
        # 物理 → 逻辑，并记住落在哪块屏
        state.from_physical(final, dpi)
        host_monitor = geometry.monitor_at(
            monitors, final.left + final.width // 2, final.top + final.height // 2
        )
        if host_monitor is not None and host_monitor.name:
            state.monitor = host_monitor.name
        settings.save(root, state)

    try:
        rect_path.unlink(missing_ok=True)
    except OSError:
        pass

    if code not in (csharp_host.EXIT_OK,):
        print(csharp_host.describe_exit(code))
    return code
