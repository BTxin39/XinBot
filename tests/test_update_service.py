"""更新检查的契约测试。

版本比较是最容易出隐蔽 bug 的地方（`0.10` vs `0.9`、`0.3.0-beta` vs `0.3.0`），
所以这里覆盖得比较密。另外要保证**任何异常输入都不抛错**：
更新检查失败不该让整个 CLI 崩掉。
"""

import json

import pytest

from app.services import update_service as update
from app.services.update_service import (
    UpdateManifest,
    check,
    is_newer,
    load_manifest,
    normalize,
    parse_manifest,
    parse_version,
)


class TestParseVersion:
    @pytest.mark.parametrize("value,expected", [
        ("0.2.0", (0, 2, 0, 0, 1)),
        ("v0.2.0", (0, 2, 0, 0, 1)),
        ("0.2", (0, 2, 0, 0, 1)),
        ("1", (1, 0, 0, 0, 1)),
        ("  v1.2.3  ", (1, 2, 3, 0, 1)),
    ])
    def test_parses_plain_versions(self, value, expected):
        assert parse_version(value) == expected

    def test_prerelease_is_lower_than_release(self):
        assert parse_version("0.3.0-beta.1") < parse_version("0.3.0")

    @pytest.mark.parametrize("value", ["", "abc", "1.2.3.4.5", "v", None, 1.2])
    def test_invalid_returns_none(self, value):
        assert parse_version(value) is None


class TestIsNewer:
    @pytest.mark.parametrize("candidate,current,expected", [
        ("0.2.1", "0.2.0", True),
        ("0.3.0", "0.2.9", True),
        ("0.10.0", "0.9.0", True),     # 字符串比较会错，必须按数字
        ("1.0.0", "0.99.99", True),
        ("0.2.0", "0.2.0", False),
        ("0.1.9", "0.2.0", False),
        ("0.2.0", "0.2.1", False),
        ("0.3.0-beta", "0.3.0", False),  # 预发布比正式版旧
        ("0.3.0", "0.3.0-beta", True),
    ])
    def test_compare(self, candidate, current, expected):
        assert is_newer(candidate, current) is expected

    def test_unparseable_is_never_newer(self):
        """解析失败时保守返回 False——不能因为清单写错就提示"有新版本"。"""
        assert is_newer("garbage", "0.2.0") is False
        assert is_newer("0.3.0", "garbage") is False


class TestManifest:
    def test_from_dict_ok(self):
        manifest = UpdateManifest.from_dict({
            "version": "v0.2.1",
            "url": "https://x/y.zip",
            "notes": "修复",
            "published": "2026-05-01",
        })
        assert manifest is not None
        assert manifest.version == "0.2.1"      # v 前缀被去掉
        assert manifest.url.endswith("y.zip")

    @pytest.mark.parametrize("raw", [
        {}, {"version": ""}, {"version": "abc"}, {"version": 1}, "not a dict",
    ])
    def test_from_dict_rejects_bad(self, raw):
        assert UpdateManifest.from_dict(raw) is None  # type: ignore[arg-type]

    def test_parse_manifest_handles_broken_json(self):
        assert parse_manifest("{broken") is None
        assert parse_manifest("") is None
        assert parse_manifest("[]") is None

    def test_load_manifest_missing_file(self, tmp_path):
        assert load_manifest(tmp_path / "nope.json") is None

    def test_load_manifest_roundtrip(self, tmp_path):
        path = tmp_path / "update.json"
        path.write_text(json.dumps({"version": "0.2.1", "notes": "x"}), encoding="utf-8")
        manifest = load_manifest(path)
        assert manifest is not None and manifest.version == "0.2.1"


class TestCheck:
    def test_newer_returns_info(self):
        manifest = UpdateManifest(version="0.2.1", url="https://x", notes="修复")
        info = check("0.2.0", manifest)
        assert info is not None
        assert (info.current, info.latest) == ("0.2.0", "0.2.1")
        assert info.url == "https://x"

    def test_same_or_older_returns_none(self):
        assert check("0.2.0", UpdateManifest(version="0.2.0")) is None
        assert check("0.2.0", UpdateManifest(version="0.1.9")) is None

    def test_missing_manifest_returns_none(self):
        assert check("0.2.0", None) is None

    def test_info_serializes(self):
        info = check("0.2.0", UpdateManifest(version="0.2.1", url="u"))
        assert info is not None
        payload = info.as_dict()
        assert set(payload) == {"current", "latest", "url", "notes", "published"}


class TestNormalize:
    @pytest.mark.parametrize("value,expected", [
        ("v0.2.0", "0.2.0"), (" 0.2.0 ", "0.2.0"), ("V1.0", "1.0"), ("", ""),
    ])
    def test_normalize(self, value, expected):
        assert normalize(value) == expected


def test_describe_latest():
    assert "最新" in update.describe(None, "0.2.0")


def test_describe_update_mentions_fields():
    info = check("0.2.0", UpdateManifest(
        version="0.2.1", url="https://x", notes="修复了穿透", published="2026-05-01"))
    text = update.describe(info, "0.2.0")
    assert "0.2.1" in text and "修复了穿透" in text and "https://x" in text


def test_describe_without_url_still_usable():
    info = check("0.2.0", UpdateManifest(version="0.2.1"))
    assert "发布页" in update.describe(info, "0.2.0")


def test_current_version_never_raises():
    """读不到包元数据时返回默认值，调用方不该处理异常。"""
    version = update.current_version("9.9.9")
    assert isinstance(version, str) and version
