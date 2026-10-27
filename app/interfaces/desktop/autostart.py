"""开机自启（Windows 注册表 Run 项）。

设计要点：
  * 写在 **HKCU**（当前用户），不需要管理员权限，卸载时也容易清理；
  * 注册的命令用**绝对路径**，且带 `--no-tray` 之外的默认参数——
    用户从注册表启动时没有终端窗口，所以用 pythonw 语义（`CREATE_NO_WINDOW`
    由启动脚本决定，这里只登记命令行）；
  * 注册表访问通过**可注入的函数**封装，这样单元测试不需要真动注册表
    （真动注册表是不可逆的副作用，测试绝对不能碰）。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "XinBotDesktopPet"


@dataclass(frozen=True)
class AutostartEntry:
    name: str
    command: str


def build_command(entry_point: Path, repo_root: Path) -> str:
    """生成注册表里要写的命令行。

    用 `pythonw.exe` 而不是 `python.exe`：开机自启时不该弹出黑色控制台窗口。
    如果同目录没有 pythonw（非常规安装），退回 python.exe 并加 `-w` 无效，
    仍可运行，只是会闪一个控制台。
    """
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    launcher = windowless if windowless.is_file() else python
    return f'"{launcher}" "{entry_point}" start pet --autostart-launch'


# ── 注册表访问（可注入，便于测试） ────────────────────────────────

def _read_registry() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _write_registry(command: str) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)


def _delete_registry() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


class Autostart:
    """开机自启的读写门面。

    默认使用真实注册表；测试里注入假的 `read/write/delete` 即可。
    """

    def __init__(
        self,
        read: Callable[[], str | None] = _read_registry,
        write: Callable[[str], None] = _write_registry,
        delete: Callable[[], bool] = _delete_registry,
    ):
        self._read = read
        self._write = write
        self._delete = delete

    def status(self) -> AutostartEntry | None:
        command = self._read()
        if not command:
            return None
        return AutostartEntry(name=VALUE_NAME, command=command)

    def enable(self, command: str) -> AutostartEntry:
        if not command.strip():
            raise ValueError("自启命令不能为空")
        self._write(command)
        return AutostartEntry(name=VALUE_NAME, command=command)

    def disable(self) -> bool:
        """返回是否真的删掉了条目（本来就是关的 → False）。"""
        return self._delete()

    @staticmethod
    def default_command(repo_root: Path) -> str:
        """优先用已安装的控制台脚本；没有则退回 `python -m`。"""
        scripts = Path(sys.executable).with_name("xinbot.exe")
        if scripts.is_file():
            return f'"{scripts}" start pet --autostart-launch'
        return (
            f'"{Path(sys.executable)}" -m app.interfaces.cli.app '
            f"start pet --autostart-launch"
        )
