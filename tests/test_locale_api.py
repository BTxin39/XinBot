"""语言设置接口的契约测试。

清单路径用 monkeypatch 隔离，测试不写真实 `data/locale.json`。
"""

import json

import pytest

from app.interfaces.web.routes import locale as locale_route
from app.services import i18n_service
from tests.test_web_cards import client as web_client  # noqa: F401  (pytest fixture)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(locale_route, "repo_root", lambda: tmp_path)
    return tmp_path


def test_default_locale(web_client, isolated):
    payload = web_client.get("/api/locale").json()["data"]
    assert payload["current"] == i18n_service.DEFAULT_LOCALE
    assert payload["default"] == i18n_service.DEFAULT_LOCALE


def test_available_locales_listed(web_client, isolated):
    items = web_client.get("/api/locale").json()["data"]["available"]
    codes = [item["code"] for item in items]
    assert "zh-CN" in codes and "en" in codes
    assert all(item["label"] for item in items)


def test_messages_catalog_returned(web_client, isolated):
    messages = web_client.get("/api/locale").json()["data"]["messages"]
    assert messages, "前端需要文案包，不能为空"
    assert "idle.greeting.morning" in messages


def test_switch_and_persist(web_client, isolated):
    payload = web_client.post("/api/locale", json={"locale": "en"}).json()["data"]
    assert payload["current"] == "en"
    saved = json.loads((isolated / "data" / "locale.json").read_text(encoding="utf-8"))
    assert saved["locale"] == "en"
    # 再读一次应保持
    assert web_client.get("/api/locale").json()["data"]["current"] == "en"


def test_unknown_locale_falls_back(web_client, isolated):
    payload = web_client.post("/api/locale", json={"locale": "fr"}).json()["data"]
    assert payload["current"] == i18n_service.DEFAULT_LOCALE


def test_regional_code_is_normalized(web_client, isolated):
    payload = web_client.post("/api/locale", json={"locale": "en-US"}).json()["data"]
    assert payload["current"] == "en"


def test_empty_locale_rejected_by_schema(web_client, isolated):
    assert web_client.post("/api/locale", json={"locale": ""}).status_code == 422


def test_catalog_matches_locale(web_client, isolated):
    web_client.post("/api/locale", json={"locale": "en"})
    messages = web_client.get("/api/locale").json()["data"]["messages"]
    assert "Maximum" in str(messages["agent.max_iterations"])
