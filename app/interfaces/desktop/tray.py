"""系统托盘图标（Windows）。

为什么用 pystray 而不是自己写 `Shell_NotifyIcon`：
自写需要处理窗口消息循环、图标资源、菜单句柄，约 300 行 ctypes；
pystray 在这件事上足够稳定且只有几十 KB。

可测试性：`TrayIcon` 把"菜单动作"与"图标渲染"抽成纯函数/回调，
导入本模块不会创建任何系统资源（pystray 只在 `start()` 时才加载）。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

TRAY_TITLE = "XinBot 桌宠"


@dataclass(frozen=True)
class TrayAction:
    """托盘菜单项。

    `checked` 为 None 表示不带勾选状态；
    `state_key` 指向 `TrayIcon._state` 里对应的键（用于刷新勾选）。
    """

    key: str
    label: str
    checked: bool | None = None
    state_key: str | None = None


def build_actions(always_on_top: bool, click_through: bool, autostart: bool) -> list[TrayAction]:
    """菜单结构（纯函数，便于单测）。

    勾选项放前面（状态一眼可见），分割线由渲染层在特定项前插入。
    """
    return [
        TrayAction("toggle_topmost", "始终置顶", always_on_top, "topmost"),
        TrayAction("toggle_click_through", "鼠标穿透", click_through, "click_through"),
        TrayAction("toggle_autostart", "开机自启", autostart, "autostart"),
        TrayAction("open_web", "打开完整界面"),
        TrayAction("toggle_visible", "显示 / 隐藏"),
        TrayAction("quit", "退出"),
    ]


def make_icon_image(size: int = 64):
    """画一个简单的托盘图标（纯绿色圆 + 白点）。

    不依赖外部图片资源：发布包里少一个二进制文件，也避免版权问题。
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = max(2, size // 10)
    draw.ellipse((margin, margin, size - margin, size - margin), fill=(46, 160, 67, 255))
    eye = size // 6
    draw.ellipse(
        (size // 2 - eye // 2, size // 2 - eye // 2, size // 2 + eye // 2, size // 2 + eye // 2),
        fill=(255, 255, 255, 255),
    )
    return image


class TrayIcon:
    """托盘图标控制器。

    `on_action(key)` 由外壳实现（切换置顶/穿透/自启、显示隐藏、退出）。
    """

    def __init__(self, on_action: Callable[[str], None]):
        self._on_action = on_action
        self._icon = None
        self._thread: threading.Thread | None = None
        self._state = {"topmost": True, "click_through": True, "autostart": False}

    def update_state(self, *, topmost: bool | None = None,
                     click_through: bool | None = None,
                     autostart: bool | None = None) -> None:
        """更新勾选状态并刷新菜单（在 UI 线程安全地排队）。"""
        if topmost is not None:
            self._state["topmost"] = topmost
        if click_through is not None:
            self._state["click_through"] = click_through
        if autostart is not None:
            self._state["autostart"] = autostart
        if self._icon is not None:
            try:
                self._icon.update_menu()
            except Exception:  # noqa: BLE001  图标可能已被移除
                pass

    def start(self) -> bool:
        """在后台线程启动托盘（非阻塞）。失败返回 False，不影响桌宠本体。"""
        try:
            import pystray
        except ImportError:
            return False

        actions = self._make_menu(pystray)
        try:
            self._icon = pystray.Icon(
                "xinbot", make_icon_image(), TRAY_TITLE, menu=pystray.Menu(*actions)
            )
        except Exception:  # noqa: BLE001
            return False

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:  # noqa: BLE001
                pass
            self._icon = None

    def _run(self) -> None:
        try:
            self._icon.run()
        except Exception:  # noqa: BLE001  托盘失败不应拖垮桌宠
            self._icon = None

    def _make_menu(self, pystray):
        def handler(key: str):
            def _click(icon=None, item=None):
                try:
                    self._on_action(key)
                except Exception:  # noqa: BLE001
                    pass
            return _click

        def checked_for(state_key: str):
            return lambda item: bool(self._state.get(state_key))

        items = []
        for action in build_actions(
            self._state["topmost"],
            self._state["click_through"],
            self._state["autostart"],
        ):
            # 功能项与退出项之间加一条分隔线
            if action.key in ("open_web", "toggle_visible"):
                items.append(pystray.Menu.SEPARATOR)
            items.append(
                pystray.MenuItem(
                    action.label,
                    handler(action.key),
                    checked=checked_for(action.state_key) if action.state_key else None,
                )
            )
        return items
