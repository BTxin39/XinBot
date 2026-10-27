"""C# 桌宠宿主（XinBotPet.exe）的调用与状态回读。

为什么要有这一层：
    pywebview 做不到"既渲染 WebView2 又逐像素透明"（见 DECISIONS v0.2.2 §26），
    所以真正的桌宠窗口由 `desktop/XinBotPet` 这个 C# 程序提供。
    Python 侧只负责：算好位置/尺寸（多显示器与 DPI 逻辑在 Python）、
    拉起进程、以及读回用户拖动后的最终位置。

约定：
    * 位置与尺寸传**物理像素**（C# 侧 SetWindowPos 直接使用）；
    * 退出时 C# 把窗口矩形写进 `--state` 指定的 JSON，由这里换算回逻辑像素。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.interfaces.desktop.geometry import Rect

# 相对仓库根的构建产物路径（dotnet build -c Release 的输出）
HOST_RELATIVE = "desktop/XinBotPet/bin/Release/net9.0-windows/win-x64/XinBotPet.exe"

EXIT_OK = 0
EXIT_BAD_ARGS = 2
EXIT_NO_WEBVIEW2 = 3

EXIT_MESSAGES = {
    EXIT_BAD_ARGS: "桌宠宿主参数错误",
    EXIT_NO_WEBVIEW2: "缺少 Microsoft Edge WebView2 运行时，请先安装",
}


def find_host(repo_root: Path) -> Path | None:
    """找到可用的宿主程序；没有就返回 None（调用方回退到旧实现）。

    先看仓库内的构建产物，再看随包分发的位置（将来可能把 exe 放进
    `pet/` 一起发布）。
    """
    root = Path(repo_root)
    candidates = [
        # 发布包里自带的位置（单文件发布，用户无需 .NET）
        root / "host" / "XinBotPet.exe",
        # 本地开发时的构建产物
        root / HOST_RELATIVE,
        root / "pet" / "XinBotPet.exe",
        root / "desktop" / "XinBotPet.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def build_command(
    exe: Path,
    url: str,
    rect: Rect,
    state_path: Path,
    *,
    click_through: bool = True,
    topmost: bool = True,
) -> list[str]:
    """构造宿主命令行。

    所有数值都用 `str()` 显式转换——避免 `Path` 或 float 被意外拼成
    `320.0` 这种 C# 解析不了的形式。
    """
    command = [
        str(exe),
        "--url", url,
        "--x", str(int(rect.left)),
        "--y", str(int(rect.top)),
        "--width", str(int(rect.width)),
        "--height", str(int(rect.height)),
        "--state", str(state_path),
    ]
    if not click_through:
        command.append("--no-passthrough")
    if not topmost:
        command.append("--no-topmost")
    return command


def read_state(state_path: Path) -> Rect | None:
    """读回宿主退出时写的窗口矩形（物理像素）。读不到就返回 None。"""
    path = Path(state_path)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return Rect(
            int(raw["x"]), int(raw["y"]),
            max(1, int(raw["width"])), max(1, int(raw["height"])),
        )
    except (KeyError, TypeError, ValueError):
        return None


def run(
    exe: Path,
    url: str,
    rect: Rect,
    state_path: Path,
    *,
    click_through: bool = True,
    topmost: bool = True,
) -> tuple[int, Rect | None]:
    """启动宿主并阻塞到用户关闭。

    返回 `(退出码, 关闭时的窗口矩形)`。矩形是物理像素，None 表示没拿到
    （例如进程被强杀，没能写状态）。
    """
    # 上次运行可能留下旧状态，先删掉，避免把陈旧位置当成这次的
    try:
        Path(state_path).unlink(missing_ok=True)
    except OSError:
        pass

    command = build_command(
        exe, url, rect, state_path,
        click_through=click_through, topmost=topmost,
    )
    completed = subprocess.run(command, check=False)
    return completed.returncode, read_state(state_path)


def describe_exit(code: int) -> str:
    """把宿主退出码翻译成用户能看懂的一句话。"""
    if code == EXIT_OK:
        return "桌宠已关闭"
    return EXIT_MESSAGES.get(code, f"桌宠异常退出（代码 {code}）")
