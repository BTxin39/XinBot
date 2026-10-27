"""构建「一键安装」分发包。

与 `package_release.py` 的区别：
    * 那个是**源码包**，用户要自己装 uv、自己 `uv sync`；
    * 这个是**安装包**，里面多了一键安装脚本、无窗口启动器、卸载脚本，
      用户解压后双击 `install.ps1` 就能用。

刻意**不做**成 PyInstaller 单文件 exe：
    * 依赖里有 chromadb / onnxruntime 这类带二进制和数据文件的包，
      PyInstaller 打包极易漏文件，且每次更新都要重新构建几百 MB；
    * 杀软对未签名的自解压 exe 误报率高；
    * 用户看到 `install.ps1` 还能读懂它做了什么（可审计）。

用法：
    python scripts/build_installer.py
产物：
    dist/XinBot-v{ver}-installer.zip
"""

from __future__ import annotations

import datetime
import hashlib
import json
import zipfile
from pathlib import Path

from package_release import ROOT, VERSION, release_files

INSTALLER_DIR = ROOT / "scripts" / "installer"

# 安装包在源码包基础上额外包含的文件（来自 scripts/installer/）
EXTRA_FILES = ("install.ps1", "uninstall.ps1", "XinBot.vbs")

README = """XinBot v{version} —— 一键安装版
================================

安装
----
1. 解压本压缩包到**你希望长期使用的目录**
   （不要放在临时目录，也不要直接在压缩包里运行）
2. 右键 `install.ps1` → 「使用 PowerShell 运行」
   如果系统提示禁止运行脚本，在 PowerShell 里执行：
       powershell -ExecutionPolicy Bypass -File .\\install.ps1
3. 安装脚本会：
       - 检查并安装 uv（Python 依赖管理工具）
       - 安装项目依赖（首次需要联网）
       - 在桌面和开始菜单创建「XinBot 桌宠」快捷方式
4. 双击快捷方式启动

使用
----
    网页界面：uv run xinbot start web
    终端界面：uv run xinbot start cli
    桌面桌宠：uv run xinbot start pet
    运行日志：uv run xinbot logs
    查看状态：uv run xinbot start --show

卸载
----
    .\\uninstall.ps1            删除快捷方式与开机自启（保留数据）
    .\\uninstall.ps1 -Purge     连同 data\\ 、pet\\ 、.env 一起删除

说明
----
* 不需要管理员权限；uv 与快捷方式都装在当前用户目录
* 模型与 API 密钥保存在你自己机器的本目录内，不会上传
* 桌面桌宠需要系统自带的 WebView2 运行时（Win10/11 通常已安装）
* 第三方 Live2D 模型与运行时请自行确认授权后使用

版本：{version}
"""


def installer_files(root: Path) -> list[Path]:
    """安装包内容 = 源码包内容 + 安装脚本。"""
    files = list(release_files(root))
    for name in EXTRA_FILES:
        path = INSTALLER_DIR / name
        if not path.is_file():
            raise SystemExit(f"缺少安装脚本：{path}")
        files.append(path)
    return sorted(set(files), key=lambda item: item.as_posix())


def main(output_dir: Path | None = None) -> None:
    """构建安装包。

    `output_dir` 可指定产物目录（测试用），默认 `dist/`。
    """
    dist = ROOT / "app" / "interfaces" / "web" / "static" / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("请先在 app/interfaces/web 运行 npm run build")

    files = installer_files(ROOT)
    output = Path(output_dir) if output_dir else ROOT / "dist"
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"XinBot-v{VERSION}-installer.zip"
    prefix = f"XinBot-v{VERSION}"

    hashes: dict[str, str] = {}
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            # 安装脚本来自 scripts/installer/，打包时要放到包根目录
            if path.parent == INSTALLER_DIR:
                name = path.name
                content = path.read_bytes()
            else:
                # release_files() 返回的是**相对** ROOT 的路径，
                # 而安装脚本是绝对路径，两种都要能处理。
                absolute = path if path.is_absolute() else ROOT / path
                name = absolute.relative_to(ROOT).as_posix()
                content = absolute.read_bytes()
            archive.writestr(f"{prefix}/{name}", content)
            hashes[name] = hashlib.sha256(content).hexdigest()

        # 附带一份清单样本：发布者把它放到服务器/共享盘，
        # 用户下载到 data/update.json 后就能 xinbot update check。
        manifest = json.dumps({
            "version": VERSION,
            "url": "",
            "notes": "（发布者填写本版本的下载地址与更新说明）",
            "published": datetime.date.today().isoformat(),
        }, ensure_ascii=False, indent=2)
        archive.writestr(f"{prefix}/update.json", manifest)
        hashes["update.json"] = hashlib.sha256(manifest.encode("utf-8")).hexdigest()

        page = README.format(version=VERSION)
        archive.writestr(f"{prefix}/安装说明.txt", page)
        hashes["安装说明.txt"] = hashlib.sha256(page.encode("utf-8")).hexdigest()
        archive.writestr(f"{prefix}/MANIFEST.json", json.dumps(hashes, indent=2, ensure_ascii=False))

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".sha256").write_text(f"{digest}  {target.name}\n", encoding="ascii")
    print(f"{target}\n{len(files) + 2} files\nSHA256: {digest}")


if __name__ == "__main__":
    main()
