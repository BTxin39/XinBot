"""提醒接口的契约测试。

路由依赖进程级单例 `reminder_service.book()`，所以每个用例都要换成
**带临时路径与固定时钟**的实例——否则会写真实 `data/reminders.json`，
也不可能稳定地构造"到点了"。
"""

from datetime import datetime

import pytest

from app.interfaces.web.routes import pet as pet_route
from app.services import reminder_service
from tests.test_web_cards import client as web_client  # noqa: F401  (pytest fixture)


class Clock:
    def __init__(self, moment: datetime):
        self.moment = moment

    def __call__(self):
        return self.moment


@pytest.fixture
def book(tmp_path):
    clock = Clock(datetime(2026, 5, 1, 9, 0))
    instance = reminder_service.reset_book(
        path=tmp_path / "data" / "reminders.json", clock=clock
    )
    original = pet_route.reminder_service
    yield instance, clock
    pet_route.reminder_service = original


def test_create_and_list(web_client, book):
    created = web_client.post(
        "/api/reminders", json={"text": "喝水", "at": "09:00", "repeat": "daily"}
    ).json()
    assert created["ok"] is True
    items = web_client.get("/api/reminders").json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["text"] == "喝水"
    assert items[0]["repeat"] == "daily"


def test_invalid_time_returns_error_not_500(web_client, book):
    response = web_client.post(
        "/api/reminders", json={"text": "喝水", "at": "九点", "repeat": "daily"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "HH:MM" in payload["error"]


def test_bad_repeat_returns_error(web_client, book):
    payload = web_client.post(
        "/api/reminders", json={"text": "喝水", "at": "09:00", "repeat": "weekly"}
    ).json()
    assert payload["ok"] is False


def test_empty_text_rejected_by_schema(web_client, book):
    assert web_client.post(
        "/api/reminders", json={"text": "", "at": "09:00", "repeat": "daily"}
    ).status_code == 422


def test_toggle_and_delete(web_client, book):
    created = web_client.post(
        "/api/reminders", json={"text": "喝水", "at": "09:00", "repeat": "daily"}
    ).json()["data"]["item"]

    assert web_client.put(
        f"/api/reminders/{created['id']}", json={"enabled": False}
    ).json()["data"]["changed"] is True
    assert web_client.get("/api/reminders").json()["data"]["items"][0]["enabled"] is False

    assert web_client.delete(
        f"/api/reminders/{created['id']}"
    ).json()["data"]["removed"] is True
    assert web_client.get("/api/reminders").json()["data"]["items"] == []


def test_delete_unknown_is_not_error(web_client, book):
    payload = web_client.delete("/api/reminders/nope").json()
    assert payload["ok"] is True
    assert payload["data"]["removed"] is False


def test_clear(web_client, book):
    for text in ("a", "b"):
        web_client.post("/api/reminders", json={"text": text, "at": "09:00", "repeat": "daily"})
    assert web_client.delete("/api/reminders").json()["data"]["cleared"] == 2
    assert web_client.get("/api/reminders").json()["data"]["items"] == []


def test_due_reminder_delivered_through_pet_state(web_client, book):
    """提醒通过桌宠轮询投递，不需要额外的推送通道。"""
    web_client.post("/api/reminders", json={"text": "喝水", "at": "09:00", "repeat": "daily"})
    state = web_client.get("/api/pet/state").json()["data"]
    assert state["reminder"]["text"] == "喝水"


def test_reminder_only_delivered_once(web_client, book):
    web_client.post("/api/reminders", json={"text": "喝水", "at": "09:00", "repeat": "daily"})
    assert web_client.get("/api/pet/state").json()["data"]["reminder"] is not None
    assert web_client.get("/api/pet/state").json()["data"]["reminder"] is None


def test_reminder_suppresses_idle_nudge(web_client, book):
    """同一轮里提醒优先，不要"提醒 + 搭话"一起弹。"""
    web_client.post("/api/reminders", json={"text": "喝水", "at": "09:00", "repeat": "daily"})
    state = web_client.get("/api/pet/state").json()["data"]
    assert state["reminder"] is not None
    assert state["idle_action"] is None


def test_no_reminder_means_null_field(web_client, book):
    state = web_client.get("/api/pet/state").json()["data"]
    assert "reminder" in state
    assert state["reminder"] is None


def test_once_reminder_delivery(web_client, book):
    instance, clock = book
    instance.add("开会", "2026-05-01T09:00", "once")
    assert web_client.get("/api/pet/state").json()["data"]["reminder"]["text"] == "开会"
    clock.moment = datetime(2026, 5, 2, 9, 0)
    assert web_client.get("/api/pet/state").json()["data"]["reminder"] is None
