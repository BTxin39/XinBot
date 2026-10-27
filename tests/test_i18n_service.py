"""多语言的契约测试。

重点：
    * 未知/畸形语言代码**回落默认**而不是报错（配置写错不该白屏）；
    * 漏翻的键要能回落，而不是显示 `idle.greeting.morning` 这种内部键名；
    * 待机调度器要真的按语言取文案（不能中英混搭）。
"""

import json

import pytest

from app.services import i18n_service as i18n
from app.services.idle_service import IdleScheduler, pools


class TestNormalize:
    @pytest.mark.parametrize("value,expected", [
        ("zh-CN", "zh-CN"),
        ("zh_CN", "zh-CN"),
        ("zh", "zh-CN"),
        ("zh-Hans", "zh-CN"),
        ("en", "en"),
        ("en-US", "en"),
        ("EN-gb", "en"),
        ("", "zh-CN"),
        (None, "zh-CN"),
        ("fr", "zh-CN"),
    ])
    def test_normalize(self, value, expected):
        assert i18n.normalize(value) == expected


class TestTranslate:
    def test_translates_known_key(self):
        assert i18n.t("agent.max_iterations", "en").startswith("(Maximum")
        assert "最大工具调用次数" in i18n.t("agent.max_iterations", "zh-CN")

    def test_missing_key_falls_back_to_key_name(self):
        assert i18n.t("does.not.exist", "en") == "does.not.exist"

    def test_unknown_locale_falls_back_to_default(self):
        assert i18n.t("agent.max_iterations", "fr") == i18n.t(
            "agent.max_iterations", "zh-CN")
        assert i18n.t_list("idle.greeting.morning", "fr") == i18n.t_list(
            "idle.greeting.morning", "zh-CN")

    def test_list_keys_return_lists(self):
        pool = i18n.t_list("idle.greeting.morning", "en")
        assert isinstance(pool, list) and pool

    def test_t_list_on_scalar_returns_single(self):
        assert i18n.t_list("agent.max_iterations", "en") == [
            i18n.t("agent.max_iterations", "en")
        ]

    def test_t_list_missing_returns_empty(self):
        assert i18n.t_list("nope.key", "en") == []

    def test_format_kwargs(self):
        # 现有键没有占位符，传入多余参数不应炸
        assert i18n.t("agent.max_iterations", "en", extra="x")


class TestCatalog:
    def test_catalog_covers_default_locale(self):
        catalog = i18n.catalog("en")
        assert set(catalog) >= set(i18n.MESSAGES[i18n.DEFAULT_LOCALE])

    def test_catalog_for_unknown_locale_returns_default(self):
        assert i18n.catalog("fr") == i18n.MESSAGES[i18n.DEFAULT_LOCALE]

    def test_available_lists_locales(self):
        codes = [item["code"] for item in i18n.available()]
        assert "zh-CN" in codes and "en" in codes

    def test_every_locale_defines_same_keys(self):
        """漏翻一个键会静默回落中文——用测试逼出这种遗漏。"""
        base = set(i18n.MESSAGES[i18n.DEFAULT_LOCALE])
        for code, messages in i18n.MESSAGES.items():
            missing = base - set(messages)
            assert not missing, f"{code} 缺少键 {missing}"


class TestPersistence:
    def test_default_when_missing(self, tmp_path):
        assert i18n.load(tmp_path) == i18n.DEFAULT_LOCALE

    def test_roundtrip(self, tmp_path):
        assert i18n.save(tmp_path, "en") == "en"
        assert i18n.load(tmp_path) == "en"
        payload = json.loads((tmp_path / "data" / "locale.json").read_text(encoding="utf-8"))
        assert payload["locale"] == "en"

    def test_unknown_saved_as_default(self, tmp_path):
        assert i18n.save(tmp_path, "fr") == i18n.DEFAULT_LOCALE
        assert i18n.load(tmp_path) == i18n.DEFAULT_LOCALE

    def test_corrupt_file_falls_back(self, tmp_path):
        path = tmp_path / "data" / "locale.json"
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        assert i18n.load(tmp_path) == i18n.DEFAULT_LOCALE


class TestIdlePools:
    def test_pools_have_all_buckets(self):
        for locale in ("zh-CN", "en"):
            greetings, nudges = pools(locale)
            assert greetings and nudges
            for bucket in greetings:
                assert greetings[bucket], f"{locale}/{bucket} 缺少问候语"
                assert nudges[bucket], f"{locale}/{bucket} 缺少搭话语"

    def test_pools_differ_by_locale(self):
        zh, _ = pools("zh-CN")
        en, _ = pools("en")
        assert zh["morning"] != en["morning"]


class TestSchedulerLocale:
    def test_greeting_uses_locale(self):
        from datetime import datetime

        clock = lambda: datetime(2026, 1, 1, 9, 0)  # noqa: E731
        zh = IdleScheduler(clock=clock, randomize=lambda: 0.0, locale="zh-CN").poll()
        en = IdleScheduler(clock=clock, randomize=lambda: 0.0, locale="en").poll()
        assert zh is not None and en is not None
        assert zh.text != en.text
        assert "早上好" in zh.text
        assert "morning" in en.text.lower()

    def test_state_reports_locale(self):
        assert IdleScheduler(locale="en").state()["locale"] == "en"

    def test_default_locale_is_chinese(self):
        from datetime import datetime

        action = IdleScheduler(
            clock=lambda: datetime(2026, 1, 1, 9, 0), randomize=lambda: 0.0
        ).poll()
        assert action is not None and "早上好" in action.text
