"""一键安装包的构建契约。

重点防的是"包看起来打好了，用户装不上"这类问题：
    * 安装脚本没被打进包；
    * 包里混进 `.env` / `data/` / `pet/`（隐私泄漏）；
    * `pyproject.toml` 声明了 extra 但 `uv.lock` 没同步 →
      `uv sync --frozen --extra desktop` 会直接报错（**实际踩到过**）。

所以除了结构检查，还要断言 lock 与 pyproject 一致。
"""

import json
import os
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DIR = ROOT / "scripts" / "installer"


def test_installer_assets_exist():
    for name in ("install.ps1", "uninstall.ps1", "XinBot.vbs"):
        assert (INSTALLER_DIR / name).is_file(), f"缺少安装脚本 {name}"


def test_installer_files_include_scripts():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from build_installer import installer_files

        files = installer_files(ROOT)
        names = {path.name for path in files}
        assert {"install.ps1", "uninstall.ps1", "XinBot.vbs"} <= names
        # 源码包该有的东西也要在
        assert any(name == "pyproject.toml" for name in names)
        assert any(name == "uv.lock" for name in names)
    finally:
        sys.path.pop(0)


def test_install_script_uses_frozen_sync():
    text = (INSTALLER_DIR / "install.ps1").read_text(encoding="utf-8")
    assert "uv sync --frozen" in text
    # 桌宠依赖失败不应中断安装
    assert "--extra desktop" in text
    assert "仍可正常使用" in text


def test_launcher_starts_the_pet():
    text = (INSTALLER_DIR / "XinBot.vbs").read_text(encoding="utf-8")
    assert "xinbot start pet" in text
    # `Run command, 0, False` → 0 是"隐藏窗口"，桌宠启动不该弹出黑框
    assert "shell.Run" in text
    assert ", 0," in text
    assert "False" in text


def test_uninstall_keeps_data_by_default():
    text = (INSTALLER_DIR / "uninstall.ps1").read_text(encoding="utf-8")
    assert "-Purge" in text
    # 默认分支必须说明数据被保留，且 Purge 需要二次确认
    assert "你的数据已保留" in text
    assert "Confirm-Action" in text
    # 卸载要清掉开机自启项，否则会留下一个坏掉的引用
    assert "XinBotDesktopPet" in text


class TestLockFileConsistency:
    """`uv.lock` 与 `pyproject.toml` 的 extras 必须一致。

    这条测试来自一个真实故障：给 pyproject 加了 `desktop` extra 但没跑 `uv lock`，
    安装包里的 `uv sync --frozen --extra desktop` 报
    "Extra `desktop` is not defined"，用户装完桌宠依赖直接失败。
    """

    def test_pyproject_declares_desktop_extra(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "desktop = [" in text
        assert "pywebview" in text
        assert "pystray" in text

    def test_lock_contains_desktop_extra(self):
        lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
        assert 'desktop = [' in lock, "uv.lock 未同步 desktop extra，请运行 uv lock"
        assert '"pywebview"' in lock
        assert '"pystray"' in lock

    def test_every_pyproject_extra_is_locked(self):
        """任何 extra 都必须在 lock 里出现，避免同类问题再犯。"""
        import tomllib

        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        extras = data.get("project", {}).get("optional-dependencies", {})
        lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
        missing = [name for name in extras if f"{name} = [" not in lock]
        assert not missing, f"这些 extra 未写入 uv.lock：{missing}"


@pytest.mark.skipif(
    not (ROOT / "app/interfaces/web/static/dist/index.html").is_file(),
    reason="需要先构建前端",
)
def test_built_installer_has_no_private_data(tmp_path):
    """真正打一次包，确认没有隐私内容混进去。"""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_installer

        build_installer.main(output_dir=tmp_path)
    finally:
        sys.path.pop(0)

    packages = list(tmp_path.glob("*installer.zip"))
    assert packages, "没有生成安装包"
    with zipfile.ZipFile(packages[0]) as archive:
        names = archive.namelist()

    forbidden = (".env", "/data/", "/pet/", "/.venv/", "/scratch/", "node_modules")
    leaked = [name for name in names if any(token in name for token in forbidden)]
    assert not leaked, f"安装包含有不应分发的文件：{leaked}"

    root_files = {name.split("/")[-1] for name in names if name.count("/") == 1}
    assert {"install.ps1", "uninstall.ps1", "XinBot.vbs"} <= root_files
    assert "安装说明.txt" in root_files
    assert "MANIFEST.json" in root_files
