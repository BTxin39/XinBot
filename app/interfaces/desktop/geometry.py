"""桌宠窗口的纯几何计算。

**不导入 win32/pywebview**：这样位置夹取、命中判断、缩放边界都能在
普通 pytest 里验证，不需要真实窗口。依赖 Windows 的部分放在 `win32_api.py`。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Monitor:
    """一个显示器的可用区域（工作区，已排除任务栏）。"""

    left: int
    top: int
    right: int
    bottom: int
    name: str = ""

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def as_rect(self) -> "Rect":
        return Rect(self.left, self.top, self.width, self.height)


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def intersection_area(self, other: "Rect") -> int:
        left = max(self.left, other.left)
        top = max(self.top, other.top)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return 0
        return (right - left) * (bottom - top)


def clamp_to_monitors(rect: Rect, monitors: list[Monitor], min_visible: int = 48) -> Rect:
    """把窗口夹回"用户抓得到"的位置。

    判定标准是**宽和高都要够**，而不是面积够：
    一条 10×420 的竖条面积 4200 已经超过阈值，但用户根本捏不住它。
    这类窗口丢在屏幕边缘的 bug 就是这么来的。

    规则：
      1. 若与某显示器的可见部分宽高都 >= min_visible，原样返回；
      2. 否则移动到**交集最大**的显示器内（保持尺寸）；
      3. 没有显示器（异常情况）时按原点保守处理。
    """
    if not monitors:
        return Rect(0, 0, rect.width, rect.height)

    def visible_size(monitor: Monitor) -> tuple[int, int]:
        left = max(rect.left, monitor.left)
        top = max(rect.top, monitor.top)
        right = min(rect.right, monitor.right)
        bottom = min(rect.bottom, monitor.bottom)
        return max(0, right - left), max(0, bottom - top)

    best = max(monitors, key=lambda monitor: visible_size(monitor)[0] * visible_size(monitor)[1])
    width, height = visible_size(best)
    if width >= min_visible and height >= min_visible:
        return rect

    # 夹到该显示器内部，同时保证整个窗口尽量在屏内
    left = max(best.left, min(rect.left, best.right - rect.width))
    top = max(best.top, min(rect.top, best.bottom - rect.height))
    return Rect(left, top, rect.width, rect.height)


def scale_for_monitor(rect: Rect, monitor: Monitor, margin: int = 8) -> Rect:
    """确保窗口不大于显示器工作区（超出则等比缩小并居中）。"""
    max_width = max(1, monitor.width - margin * 2)
    max_height = max(1, monitor.height - margin * 2)
    if rect.width <= max_width and rect.height <= max_height:
        return rect
    ratio = min(max_width / rect.width, max_height / rect.height)
    width = max(1, int(rect.width * ratio))
    height = max(1, int(rect.height * ratio))
    left = monitor.left + (monitor.width - width) // 2
    top = monitor.top + (monitor.height - height) // 2
    return Rect(left, top, width, height)


def clamp_scale(scale: float, lowest: float = 0.4, highest: float = 3.0) -> float:
    """缩放限制在合理区间，避免用户把角色缩成看不见或撑满屏幕。"""
    return max(lowest, min(highest, float(scale)))


# ── 显示器查找与 DPI 换算 ─────────────────────────────────────────

def find_monitor(monitors: list[Monitor], name: str) -> Monitor | None:
    """按设备名找显示器（用户拔掉副屏后要能识别"原来那块不在了"）。"""
    if not name:
        return None
    for monitor in monitors:
        if monitor.name and monitor.name == name:
            return monitor
    return None


def monitor_at(monitors: list[Monitor], x: int, y: int) -> Monitor | None:
    """坐标落在哪个显示器上；不在任何屏内时返回交集最大的那块。"""
    for monitor in monitors:
        if monitor.contains(x, y):
            return monitor
    if not monitors:
        return None
    return max(
        monitors,
        key=lambda monitor: Rect(monitor.left, monitor.top, monitor.width, monitor.height)
        .intersection_area(Rect(x, y, 1, 1)),
    )


def scale_rect(rect: Rect, factor: float) -> Rect:
    """按比例缩放矩形（用于逻辑像素 ↔ 物理像素换算）。"""
    if factor <= 0:
        return rect
    return Rect(
        int(round(rect.left * factor)),
        int(round(rect.top * factor)),
        max(1, int(round(rect.width * factor))),
        max(1, int(round(rect.height * factor))),
    )


def bottom_right(monitor: Monitor, width: int, height: int, margin: int = 48) -> Rect:
    """放到显示器右下角——桌宠最自然的位置。"""
    return Rect(
        monitor.right - width - margin,
        monitor.bottom - height - margin,
        width,
        height,
    )


def hit_test(
    cursor_x: int,
    cursor_y: int,
    window: Rect,
    content: Rect | None,
    alpha_ratio: float | None = None,
    alpha_threshold: float = 0.02,
) -> bool:
    """判断光标是否"按到了角色"。

    参数：
        window  —— 窗口在屏幕上的矩形
        content —— 角色画布在窗口内的矩形（来自前端 `bounds()`），None 表示未知
        alpha_ratio —— 该点周围的不透明像素占比（0~1）。
                      **None = 还没有掩码数据**（与"确实是透明像素"的 0.0 区分开）
        alpha_threshold —— 低于此占比视为点在透明区域

    设计说明：
      * content 未知时退化为"整个窗口都算角色"，宁可多响应也不要完全点不到；
      * alpha_ratio 为 None 时只按矩形判断；给出具体值（含 0.0）就按阈值过滤。
        早期实现把 0.0 当成"未知"，导致点在角色外的透明角落也会被当成命中。
    """
    if not window.contains(cursor_x, cursor_y):
        return False
    if content is None:
        return True

    local_x = cursor_x - window.left
    local_y = cursor_y - window.top
    if not Rect(0, 0, window.width, window.height).contains(local_x, local_y):
        return False

    if not Rect(content.left, content.top, content.width, content.height).contains(
        local_x, local_y
    ):
        return False
    if alpha_ratio is None:
        return True
    return alpha_ratio >= alpha_threshold
