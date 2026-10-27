"""Win32 窗口样式操作（只在 Windows 上可用）。

把 ctypes/win32 调用集中在这里，`shell.py` 只调用本模块的语义化函数。
所有函数都对"窗口句柄无效"做保护：桌宠启动早期 HWND 可能还没就绪。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from app.interfaces.desktop.geometry import Monitor, Rect

GWL_EXSTYLE = -20
GWL_STYLE = -16

WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_APPWINDOW = 0x00040000

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02

SW_SHOWNOACTIVATE = 4

LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002

_user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None


def available() -> bool:
    """当前平台是否能做窗口操作。"""
    return _user32 is not None


def ensure_dpi_aware() -> str:
    """声明进程 DPI 感知，统一坐标系。

    **这是必须的**：非 DPI 感知进程里，
    `EnumDisplayMonitors` 返回的 `rcWork` 是逻辑像素，
    而 `GetWindowRect` / `SetWindowPos` 拿到的是物理像素，两者混用会让
    保存的位置落到屏幕外（实测：工作区宽 1707，却存下了 x=2107），
    重启后窗口被夹来夹去、尺寸对不上，最终表现为"窗口在但什么都不画"。

    返回采用的方式，便于日志记录。
    """
    if _user32 is None:
        return "unsupported"
    # 2 = PROCESS_PER_MONITOR_DPI_AWARE（Win8.1+）
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except Exception:  # noqa: BLE001
        pass
    try:
        _user32.SetProcessDPIAware()
        return "system"
    except Exception:  # noqa: BLE001
        return "none"


def dpi_scale(hwnd: int = 0) -> float:
    """当前缩放比例（96 DPI 为 1.0）。用于把物理像素换算成 CSS 像素。"""
    if _user32 is None:
        return 1.0
    try:
        dpi = _user32.GetDpiForWindow(hwnd) if hwnd else 0
    except Exception:  # noqa: BLE001
        dpi = 0
    if not dpi:
        try:
            dpi = _user32.GetDpiForSystem()
        except Exception:  # noqa: BLE001
            dpi = 96
    return (dpi or 96) / 96.0


def dpi_for_point(x: int, y: int) -> float:
    """某个坐标所在显示器的缩放比例。

    多显示器混合 DPI（例如笔记本 150% + 外接 100%）时，
    **不能用系统 DPI**：那样窗口在另一块屏上大小会明显不对。
    """
    if _user32 is None:
        return 1.0
    try:
        monitor = _user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)  # NEAREST
        if monitor:
            dpi_x = ctypes.c_uint(96)
            dpi_y = ctypes.c_uint(96)
            # MDT_EFFECTIVE_DPI = 0
            if ctypes.windll.shcore.GetDpiForMonitor(
                monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
            ) == 0:
                return max(0.5, min(4.0, dpi_x.value / 96.0))
    except Exception:  # noqa: BLE001
        pass
    return dpi_scale()


def dpi_for_monitor(monitor: Monitor) -> float:
    """显示器中心点所在位置的缩放比例。"""
    return dpi_for_point(
        monitor.left + monitor.width // 2,
        monitor.top + monitor.height // 2,
    )


def _get(hwnd: int, index: int) -> int:
    if not hwnd:
        return 0
    return _user32.GetWindowLongW(hwnd, index)


def _set(hwnd: int, index: int, value: int) -> None:
    if hwnd:
        _user32.SetWindowLongW(hwnd, index, value)


def make_frameless_toolwindow(hwnd: int) -> None:
    """去掉标题栏/边框，并设为工具窗（不占任务栏、不参与 Alt+Tab）。"""
    style = _get(hwnd, GWL_STYLE) & ~(WS_CAPTION | WS_THICKFRAME)
    _set(hwnd, GWL_STYLE, style)
    ex = _get(hwnd, GWL_EXSTYLE)
    _set(hwnd, GWL_EXSTYLE, (ex | WS_EX_LAYERED | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)


def set_topmost(hwnd: int, enabled: bool) -> None:
    if not hwnd:
        return
    _user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST if enabled else HWND_NOTOPMOST,
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


def set_color_key(hwnd: int, rgb: tuple[int, int, int] = (255, 0, 255)) -> bool:
    """把指定颜色设为"透明键"（`LWA_COLORKEY`）。

    为什么不用 WinForms 的 `TransparencyKey`：
    它靠**窗口区域（region）裁剪**实现，而 WebView2 是独立子 HWND 自己绘制，
    region 会把整个子窗口裁掉 —— 实测表现为"页面已加载、模型已请求，
    但窗口一片空白"，且时好时坏。
    `LWA_COLORKEY` 由 DWM 在**合成阶段**逐像素判定，对子窗口渲染同样有效。
    """
    if not hwnd:
        return False
    ex = _get(hwnd, GWL_EXSTYLE)
    _set(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
    color = rgb[0] | (rgb[1] << 8) | (rgb[2] << 16)  # COLORREF 是 BGR 顺序
    return bool(_user32.SetLayeredWindowAttributes(hwnd, color, 0, LWA_COLORKEY))


def set_click_through(hwnd: int, enabled: bool) -> bool:
    """切换鼠标穿透，返回**读回**的实际状态（而不是我们以为设置成功的值）。"""
    if not hwnd:
        return False
    ex = _get(hwnd, GWL_EXSTYLE)
    new = (ex | WS_EX_TRANSPARENT) if enabled else (ex & ~WS_EX_TRANSPARENT)
    _set(hwnd, GWL_EXSTYLE, new | WS_EX_LAYERED)
    return bool(_get(hwnd, GWL_EXSTYLE) & WS_EX_TRANSPARENT)


def is_click_through(hwnd: int) -> bool:
    return bool(_get(hwnd, GWL_EXSTYLE) & WS_EX_TRANSPARENT)


def find_window_by_title(title: str, timeout: float = 0.0) -> int:
    """按标题查找顶层窗口句柄；找不到返回 0。

    为什么不用 pywebview 的 `window.native`：
    那个对象在窗口创建完成前可能为空、`Handle` 也可能还是 0，
    取决于 pywebview 内部时序（P2 实测踩到：`native` 拿到的句柄恒为 0，
    而窗口其实已经存在）。按标题枚举是确定性的，spike 阶段验证可靠。
    """
    import time as _time

    deadline = _time.monotonic() + timeout
    while True:
        found: list[int] = []

        def callback(hwnd, _):
            length = _user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                _user32.GetWindowTextW(hwnd, buffer, length + 1)
                if buffer.value == title or title in buffer.value:
                    found.append(hwnd)
            return True

        try:
            _user32.EnumWindows(
                ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(callback), 0
            )
        except Exception:  # noqa: BLE001
            return 0

        if found:
            return found[0]
        if _time.monotonic() >= deadline:
            return 0
        _time.sleep(0.1)


def show_window(hwnd: int) -> bool:
    """显示窗口但不抢焦点。

    必须显式调用：pywebview 在 `transparent=True` 时会先用
    "隐藏 → 等 Navigating 事件再显示"的 hack（见其 winforms.py），
    用 URL（而不是内联 html）加载时该事件可能不触发，
    结果窗口一直隐藏（`IsWindowVisible` 为 0）——P2 实际踩到过。
    """
    if not hwnd:
        return False
    return bool(_user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE))


def is_visible(hwnd: int) -> bool:
    return bool(hwnd) and bool(_user32.IsWindowVisible(hwnd))


def window_rect(hwnd: int) -> Rect | None:
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return Rect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def move_window(hwnd: int, x: int, y: int) -> None:
    if not hwnd:
        return
    _user32.SetWindowPos(hwnd, 0, int(x), int(y), 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)


def resize_window(hwnd: int, width: int, height: int) -> None:
    if not hwnd:
        return
    _user32.SetWindowPos(hwnd, 0, 0, 0, int(width), int(height), SWP_NOMOVE | SWP_NOACTIVATE)


def cursor_pos() -> tuple[int, int]:
    point = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def left_button_down() -> bool:
    return bool(_user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)


def right_button_down() -> bool:
    return bool(_user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000)


def dpi_for_rect(rect: Rect) -> float:
    """矩形中心所在显示器的缩放比例（窗口跨屏时以中心为准）。"""
    return dpi_for_point(
        rect.left + rect.width // 2,
        rect.top + rect.height // 2,
    )


def _monitor_name(device) -> str:
    """把 `szDevice`（宽字符数组）转成字符串，失败返回空串。"""
    try:
        return str(device).strip() or ""
    except Exception:  # noqa: BLE001
        return ""


def monitors() -> list[Monitor]:
    """枚举所有显示器的工作区（已排除任务栏）。

    **内部会先确保 DPI 感知**：非 DPI 感知进程拿到的坐标会被系统虚拟化成
    逻辑像素（实测 2560×1600 的屏报成 1707×1019），和 `GetWindowRect` 的
    物理像素混用就会把窗口算到屏幕外。让本函数自己保证顺序，调用方不必记。

    失败时回落到"一个 1920×1080 工作区"，保证调用方不必处理空列表。
    """
    ensure_dpi_aware()
    found: list[Monitor] = []
    if _user32 is not None:
        monitor_enum = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(wintypes.RECT), ctypes.c_double,
        )

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        def callback(handle, _hdc, _rect, _data):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if _user32.GetMonitorInfoW(handle, ctypes.byref(info)):
                work = info.rcWork
                # szDevice 形如 \\.\DISPLAY1，用于"记住上次在哪块屏"
                name = _monitor_name(info.szDevice)
                found.append(Monitor(work.left, work.top, work.right, work.bottom, name))
            return 1

        try:
            _user32.EnumDisplayMonitors(None, None, monitor_enum(callback), 0)
        except Exception:  # noqa: BLE001  枚举失败不应让桌宠起不来
            found.clear()

    return found or [Monitor(0, 0, 1920, 1040)]


def primary_monitor(monitors_list: list[Monitor]) -> Monitor:
    """主屏近似：包含原点 (0,0) 的那块；没有则取第一块。"""
    for monitor in monitors_list:
        if monitor.left <= 0 < monitor.right and monitor.top <= 0 < monitor.bottom:
            return monitor
    return monitors_list[0]
