"""版本检查与更新提示。

**刻意的边界：不做静默自替换。**
替换正在运行的程序文件（尤其 Windows 上被占用的 exe/dll）需要在重启后由
另一个进程搬文件，一旦中途失败用户就没有可用的程序了。所以这里只做
"检查 + 下载 + 告诉用户怎么做"，把决定权留给用户。

清单格式（`update.json`）：

    {
      "version": "0.2.1",
      "url": "https://example.com/XinBot-v0.2.1-installer.zip",
      "notes": "修复了桌面壳的穿透问题",
      "published": "2026-05-01",
      "sha256": "…（可选）"
    }
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# 版本号只接受 1~4 段数字，可带 prerelease 后缀（如 0.3.0-beta.1）
_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+){0,3})(?:[-+]([0-9A-Za-z.\-]+))?$")


def parse_version(value: str) -> tuple[int, ...] | None:
    """把 `v0.2.1` / `0.2` / `0.2.1-beta.1` 解析成可比较的元组。

    prerelease 用 `(0,)` 表示"比同版本正式版小"，这样
    `0.3.0-beta < 0.3.0`，符合直觉。
    解析失败返回 None（调用方负责报错，不要静默当成最新）。
    """
    if not isinstance(value, str):
        return None
    match = _VERSION_RE.match(value.strip())
    if not match:
        return None
    numbers = tuple(int(part) for part in match.group(1).split("."))
    suffix = match.group(2)
    # 补齐到 4 段，避免 (0,2) 与 (0,2,0) 比较出错
    numbers = numbers + (0,) * (4 - len(numbers))
    if suffix:
        return numbers + (0,)
    return numbers + (1,)


def is_newer(candidate: str, current: str) -> bool:
    """`candidate` 是否比 `current` 新。任一无法解析时返回 False（保守）。"""
    left = parse_version(candidate)
    right = parse_version(current)
    if left is None or right is None:
        return False
    return left > right


def normalize(value: str) -> str:
    """统一展示形态：去掉前缀 v，去空白。"""
    return (value or "").strip().lstrip("vV")


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    url: str = ""
    notes: str = ""
    published: str = ""
    sha256: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "UpdateManifest | None":
        if not isinstance(raw, dict):
            return None
        version = raw.get("version")
        if not isinstance(version, str) or parse_version(version) is None:
            return None
        return cls(
            version=normalize(version),
            url=str(raw.get("url") or "").strip(),
            notes=str(raw.get("notes") or "").strip(),
            published=str(raw.get("published") or "").strip(),
            sha256=str(raw.get("sha256") or "").strip(),
        )


@dataclass(frozen=True)
class UpdateInfo:
    """有新版本时的结果。"""

    current: str
    latest: str
    url: str
    notes: str
    published: str

    def as_dict(self) -> dict:
        return {
            "current": self.current,
            "latest": self.latest,
            "url": self.url,
            "notes": self.notes,
            "published": self.published,
        }


def current_version(default: str = "0.0.0") -> str:
    """读已安装包的版本；读不到时返回 `default` 而不是抛错。"""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("xinbot")
    except Exception:  # noqa: BLE001  PackageNotFoundError / 任何元数据问题
        return default


def check(current: str, manifest: UpdateManifest | None) -> UpdateInfo | None:
    """比较版本；有更新返回 UpdateInfo，否则 None。"""
    if manifest is None:
        return None
    if not is_newer(manifest.version, current):
        return None
    return UpdateInfo(
        current=normalize(current),
        latest=manifest.version,
        url=manifest.url,
        notes=manifest.notes,
        published=manifest.published,
    )


def load_manifest(source: str | Path) -> UpdateManifest | None:
    """从本地文件读清单。

    不在这里做网络请求：更新检查应当是**用户显式触发**的动作，
    不该在后台悄悄联网。需要远程清单时，由调用方先下载再用本函数解析内容
    （见 `parse_manifest`）。
    """
    path = Path(source)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_manifest(text)


def parse_manifest(text: str) -> UpdateManifest | None:
    """解析清单文本；格式不对返回 None（不抛异常）。"""
    try:
        raw = json.loads(text)
    except (TypeError, ValueError):
        return None
    return UpdateManifest.from_dict(raw)


def describe(info: UpdateInfo | None, current: str) -> str:
    """给 CLI 用的一句话说明。"""
    if info is None:
        return f"已是最新版本（{normalize(current)}）"
    parts = [f"发现新版本 {info.current} → {info.latest}"]
    if info.published:
        parts.append(f"发布日期：{info.published}")
    if info.notes:
        parts.append(f"更新说明：{info.notes}")
    if info.url:
        parts.append(f"下载地址：{info.url}")
    else:
        parts.append("清单里没有下载地址，请到发布页获取")
    return "\n".join(parts)
