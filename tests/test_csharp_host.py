"""C# 桌宠宿主的调用契约。

宿主是一个外部 exe，测试不能真的启动它（会弹窗、要 WebView2），
所以这里覆盖的是**可测的那部分**：命令构造、状态回读、宿主发现、退出码翻译。

这些恰恰是最容易出错的地方：参数拼错一个字符，宿主就静默不显示；
状态回读容错没做好，用户拖过的位置就会丢。
"""

import json

import pytest

from app.interfaces.desktop import csharp_host
from app.interfaces.desktop.geometry import Rect


def test_find_host_returns_none_when_missing(tmp_path):
    assert csharp_host.find_host(tmp_path) is None


def test_find_host_prefers_repo_build(tmp_path):
    target = tmp_path / csharp_host.HOST_RELATIVE
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MZ")
    assert csharp_host.find_host(tmp_path) == target


def test_find_host_falls_back_to_bundled(tmp_path):
    bundled = tmp_path / "pet" / "XinBotPet.exe"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"MZ")
    assert csharp_host.find_host(tmp_path) == bundled


def test_build_command_contains_all_fields():
    command = csharp_host.build_command(
        exe=__import__("pathlib").Path("C:/x/XinBotPet.exe"),
        url="http://127.0.0.1:3796/#/pet",
        rect=Rect(900, 300, 480, 630),
        state_path=__import__("pathlib").Path("C:/x/state.json"),
    )
    assert command[0].endswith("XinBotPet.exe")
    assert "--url" in command and "http://127.0.0.1:3796/#/pet" in command
    assert command[command.index("--x") + 1] == "900"
    assert command[command.index("--y") + 1] == "300"
    assert command[command.index("--width") + 1] == "480"
    assert command[command.index("--height") + 1] == "630"
    assert "--state" in command


def test_build_command_flags():
    base = dict(
        exe=__import__("pathlib").Path("XinBotPet.exe"),
        url="http://x/",
        rect=Rect(0, 0, 320, 420),
        state_path=__import__("pathlib").Path("s.json"),
    )
    with_flags = csharp_host.build_command(**base, click_through=False, topmost=False)
    assert "--no-passthrough" in with_flags
    assert "--no-topmost" in with_flags

    without = csharp_host.build_command(**base, click_through=True, topmost=True)
    assert "--no-passthrough" not in without
    assert "--no-topmost" not in without


def test_build_command_uses_integers():
    """C# 侧只接受整数；传 320.0 会解析失败并静默不显示。"""
    command = csharp_host.build_command(
        exe=__import__("pathlib").Path("x.exe"),
        url="http://x/",
        rect=Rect(10.7, 20.2, 320.9, 420.1),  # type: ignore[arg-type]
        state_path=__import__("pathlib").Path("s.json"),
    )
    assert command[command.index("--x") + 1] == "10"
    assert command[command.index("--width") + 1] == "320"


class TestReadState:
    def test_missing_file(self, tmp_path):
        assert csharp_host.read_state(tmp_path / "none.json") is None

    def test_valid(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"x": 900, "y": 300, "width": 480, "height": 630}),
                        encoding="utf-8")
        assert csharp_host.read_state(path) == Rect(900, 300, 480, 630)

    def test_corrupt_json(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text("{not json", encoding="utf-8")
        assert csharp_host.read_state(path) is None

    def test_missing_fields(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"x": 1}), encoding="utf-8")
        assert csharp_host.read_state(path) is None

    def test_zero_size_is_clamped(self, tmp_path):
        """宿主异常退出时可能写出 0 尺寸，不能让状态变成不可见窗口。"""
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"x": 0, "y": 0, "width": 0, "height": 0}),
                        encoding="utf-8")
        rect = csharp_host.read_state(path)
        assert rect is not None
        assert rect.width >= 1 and rect.height >= 1


def test_describe_exit_codes():
    assert "关闭" in csharp_host.describe_exit(csharp_host.EXIT_OK)
    assert "WebView2" in csharp_host.describe_exit(csharp_host.EXIT_NO_WEBVIEW2)
    assert "参数" in csharp_host.describe_exit(csharp_host.EXIT_BAD_ARGS)
    assert "7" in csharp_host.describe_exit(7)
