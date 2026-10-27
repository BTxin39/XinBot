"""桌宠窗口的本地状态持久化（`data/desktop_pet.json`）。

**为什么不放 `runtime_config.json`**：
那是 `RuntimeConfig` 的字段白名单（DECISIONS_V0.2.0 D2）管的业务配置，
桌面窗口的位置/缩放属于界面状态，混进去会污染白名单并影响 Web 端读写。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.interfaces.desktop.geometry import (
    Monitor,
    Rect,
    bottom_right,
    clamp_scale,
    clamp_to_monitors,
    find_monitor,
    monitor_at,
    scale_rect,
)

DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 420


@dataclass
class PetWindowState:
    """桌宠窗口的可持久化状态。

    **尺寸以逻辑（CSS）像素存储**，另存当时的 `dpi`。
    原因：物理像素在不同缩放的显示器上含义不同——把 458×574 的物理尺寸
    原样搬到 100% 缩放的屏幕上，窗口会明显偏大。按逻辑像素存、按当前 DPI
    还原，用户看到的"大小"才是一致的。
    """

    visible: bool = True
    x: int = -1
    y: int = -1
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    scale: float = 1.0
    always_on_top: bool = True
    click_through: bool = True
    monitor: str = ""
    dpi: float = 0.0  # 0 表示"旧版本文件"，加载时按物理像素迁移

    def rect(self) -> Rect:
        """逻辑像素矩形。"""
        return Rect(self.x, self.y, self.width, self.height)

    def to_physical(self, dpi: float = 1.0) -> Rect:
        """逻辑 → 物理，用于创建/移动原生窗口。"""
        return scale_rect(self.rect(), dpi or 1.0)

    def from_physical(self, rect: Rect, dpi: float = 1.0) -> None:
        """物理 → 逻辑，用于把 `GetWindowRect` 的结果存回去。"""
        logical = scale_rect(rect, 1.0 / (dpi or 1.0))
        self.x, self.y = logical.left, logical.top
        self.width, self.height = logical.width, logical.height
        self.dpi = float(dpi or 1.0)

    def restore(self, monitors: list[Monitor], margin: int = 48, dpi: float = 1.0) -> Rect:
        """计算窗口应当出现的矩形（**物理像素**，可直接交给窗口 API）。

        坐标系约定（实测得出，别改）：
          * `monitors` 传的是**物理**工作区（`win32_api.monitors()`）；
          * 状态里的 x/y/width/height 是**逻辑**像素；
          * 返回物理像素——DPI 感知进程里，pywebview 把传入值当物理值用。

        优先级：
          1. 保存过显示器且它还在 → 放回那块屏；
          2. 从未定位过 → 主屏右下角；
          3. 其它 → 用保存的位置并夹回可见区域。
        """
        scale = float(dpi or 1.0)
        if not monitors:
            return self.to_physical(scale)

        # 物理 → 逻辑，便于用逻辑尺寸做夹取判断
        logical_monitors = [
            Monitor(
                int(round(m.left / scale)),
                int(round(m.top / scale)),
                int(round(m.right / scale)),
                int(round(m.bottom / scale)),
                m.name,
            )
            for m in monitors
        ]

        saved_monitor = find_monitor(logical_monitors, self.monitor)
        if self.x < 0 or self.y < 0:
            target = saved_monitor or logical_monitors[0]
            logical = bottom_right(target, self.width, self.height, margin)
        else:
            logical = clamp_to_monitors(self.rect(), logical_monitors)

        self.x, self.y = logical.left, logical.top
        return scale_rect(logical, scale)

    def normalized(self) -> "PetWindowState":
        """把可能损坏/越界/类型错误的字段收敛成可用值。

        配置文件是给人看的，用户会手改、旧版本会写别的字段，
        所以这里必须容忍 None/字符串/负数，绝不抛异常——
        一个写坏的位置字段不该让桌宠起不来。
        """
        def as_int(value, fallback: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return fallback

        def as_float(value, fallback: float) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return fallback

        return PetWindowState(
            visible=bool(self.visible),
            x=as_int(self.x, -1),
            y=as_int(self.y, -1),
            width=max(80, as_int(self.width, DEFAULT_WIDTH)),
            height=max(80, as_int(self.height, DEFAULT_HEIGHT)),
            scale=clamp_scale(as_float(self.scale, 1.0)),
            always_on_top=bool(self.always_on_top),
            click_through=bool(self.click_through),
            monitor=str(self.monitor or ""),
            dpi=max(0.0, as_float(self.dpi, 0.0)),
        )


def state_path(repo_root: Path) -> Path:
    return Path(repo_root) / "data" / "desktop_pet.json"


def load(repo_root: Path) -> PetWindowState:
    """读取状态；文件缺失/损坏/字段多余都回落到默认值，绝不抛给调用方。

    兼容旧文件：没有 `dpi` 字段的老文件，其 width/height 是**物理像素**。
    这里不立刻换算（当时不知道 DPI），交给 `restore(dpi=...)` 的调用方处理：
    若 `dpi == 0`，视作逻辑值，按 1:1 使用。
    """
    path = state_path(repo_root)
    if not path.is_file():
        return PetWindowState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return PetWindowState()
    if not isinstance(raw, dict):
        return PetWindowState()

    known = {field for field in PetWindowState.__dataclass_fields__}
    data = {key: value for key, value in raw.items() if key in known}
    try:
        return PetWindowState(**data).normalized()
    except (TypeError, ValueError):
        return PetWindowState()


def save(repo_root: Path, state: PetWindowState) -> Path:
    """原子写入（先写临时文件再替换），避免崩溃时留下半个 JSON。"""
    path = state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(state.normalized()), ensure_ascii=False, indent=2)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    return path
