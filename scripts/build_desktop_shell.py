"""构建 C# 桌宠宿主（`desktop/XinBotPet`）。

为什么需要单独一步：
    桌宠窗口由 C# 程序提供（pywebview 做不到"既渲染 WebView2 又逐像素透明"），
    它得先编译出 exe，`xinbot start pet` 才能用上。不构建时 Python 侧会回退到
    旧实现（不透明），并给出提示。

用法：
    python scripts/build_desktop_shell.py            # Release 构建
    python scripts/build_desktop_shell.py --clean    # 先清理再构建

前置：
    * .NET SDK 8/9（`dotnet --version` 能跑通）
    * 首次构建需要联网还原 `Microsoft.Web.WebView2` 包
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT / "desktop" / "XinBotPet"
PROJECT = PROJECT_DIR / "XinBotPet.csproj"
# 与 app/interfaces/desktop/csharp_host.py 里的 HOST_RELATIVE 保持一致
# 单文件发布产物：随发布包分发到 host/，用户无需安装 .NET
PUBLISH_DIR = ROOT / "host"
OUTPUT = PUBLISH_DIR / "XinBotPet.exe"


def dotnet_available() -> bool:
    return shutil.which("dotnet") is not None


def main(argv: list[str]) -> int:
    if not dotnet_available():
        print("未找到 dotnet。请先安装 .NET SDK：https://dotnet.microsoft.com/download", file=sys.stderr)
        return 1
    if not PROJECT.is_file():
        print(f"缺少工程文件：{PROJECT}", file=sys.stderr)
        return 1

    if "--clean" in argv:
        for name in ("bin", "obj"):
            target = PROJECT_DIR / name
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
                print(f"已清理 {target.relative_to(ROOT)}")

    # -nologo 减少噪音；构建输出直接透传，失败时用户能看到具体错误
    # 用 publish 而不是 build：build 的产物是一堆 DLL，用户那边缺一个就起不来；
    # publish 打成**单文件 exe**（含原生库自解压），拷过去就能跑。
    completed = subprocess.run(
        ["dotnet", "publish", str(PROJECT), "-c", "Release", "-r", "win-x64",
         "--self-contained", "false", "-p:PublishSingleFile=true",
         "-p:IncludeNativeLibrariesForSelfExtract=true",
         "-o", str(PUBLISH_DIR), "-nologo"],
        cwd=str(PROJECT_DIR),
        check=False,
    )
    if completed.returncode != 0:
        print("构建失败。请检查上面的错误信息。", file=sys.stderr)
        return completed.returncode

    if OUTPUT.is_file():
        size = OUTPUT.stat().st_size / 1024
        print(f"\n构建完成：{OUTPUT.relative_to(ROOT)}（{size:.0f} KB）")
        print("现在 `xinbot start pet` 会自动使用它。")
        return 0

    print(f"构建似乎成功，但没有找到产物：{OUTPUT}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
