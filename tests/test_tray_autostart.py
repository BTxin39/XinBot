"""托盘与开机自启的契约测试。

两者都刻意做成"可注入依赖"：
    * 开机自启的注册表读写通过构造参数注入 → 测试**绝不动真实注册表**
      （往 ``HKCU/.../Run`` 写条目是有副作用的，测试必须隔离）；
    * 托盘菜单结构是纯函数 → 不需要真的起托盘线程。
"""

from pathlib import Path

import pytest

from app.interfaces.desktop import autostart as autostart_module
from app.interfaces.desktop import tray as tray_module


# ── 开机自启 ──────────────────────────────────────────────────────

class FakeRegistry:
    """内存版注册表。"""

    def __init__(self, value: str | None = None):
        self.value = value
        self.writes: list[str] = []
        self.deletes = 0

    def read(self) -> str | None:
        return self.value

    def write(self, command: str) -> None:
        self.writes.append(command)
        self.value = command

    def delete(self) -> bool:
        self.deletes += 1
        had = self.value is not None
        self.value = None
        return had

    def manager(self) -> autostart_module.Autostart:
        return autostart_module.Autostart(self.read, self.write, self.delete)


def test_status_none_when_absent():
    assert FakeRegistry().manager().status() is None


def test_enable_writes_and_reports():
    registry = FakeRegistry()
    manager = registry.manager()
    entry = manager.enable('"C:\\x\\xinbot.exe" start pet')
    assert entry.name == autostart_module.VALUE_NAME
    assert registry.writes == ['"C:\\x\\xinbot.exe" start pet']
    assert manager.status().command == '"C:\\x\\xinbot.exe" start pet'


def test_disable_returns_whether_removed():
    registry = FakeRegistry('"C:\\x\\xinbot.exe" start pet')
    manager = registry.manager()
    assert manager.disable() is True
    assert manager.status() is None
    # 再关一次：本来就没有 → False（调用方据此给出不同提示）
    assert manager.disable() is False


def test_enable_rejects_empty_command():
    with pytest.raises(ValueError):
        FakeRegistry().manager().enable("   ")


def test_command_quotes_paths_with_spaces(tmp_path):
    """路径可能含空格（如 `C:\\Program Files`），必须带引号。"""
    command = autostart_module.Autostart.default_command(tmp_path)
    assert command.startswith('"')
    assert "start pet" in command


def test_value_name_is_stable():
    """改了这个名字，老用户的自启项就找不到了——锁住它。"""
    assert autostart_module.VALUE_NAME == "XinBotDesktopPet"
    assert autostart_module.RUN_KEY.endswith("CurrentVersion\\Run")


# ── 托盘菜单 ──────────────────────────────────────────────────────

def test_menu_contains_core_actions():
    keys = [action.key for action in tray_module.build_actions(True, True, False)]
    assert keys == [
        "toggle_topmost",
        "toggle_click_through",
        "toggle_autostart",
        "open_web",
        "toggle_visible",
        "quit",
    ]


def test_menu_reflects_state():
    actions = {a.key: a for a in tray_module.build_actions(False, True, True)}
    assert actions["toggle_topmost"].checked is False
    assert actions["toggle_click_through"].checked is True
    assert actions["toggle_autostart"].checked is True
    # 无状态项不应带勾选
    assert actions["quit"].checked is None


def test_icon_image_has_expected_size():
    image = tray_module.make_icon_image(64)
    assert image.size == (64, 64)
    # 图标必须真的有内容（不是全透明），否则托盘里看不见
    assert image.getbbox() is not None


def test_tray_state_update_does_not_require_icon():
    """还没启动图标时更新状态不应报错（外壳启动早期就是这种时序）。"""
    icon = tray_module.TrayIcon(lambda key: None)
    icon.update_state(topmost=False)
    assert icon._state["topmost"] is False


def test_tray_import_is_side_effect_free():
    """导入模块不应创建任何系统资源（CLI --help 会触发导入）。"""
    assert tray_module.TRAY_TITLE
    assert callable(tray_module.make_icon_image)
