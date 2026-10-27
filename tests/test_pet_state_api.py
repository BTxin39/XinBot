"""`/api/pet/state` 与 `/api/pet/touch` 的接口契约。

待机行为挂在状态轮询上，所以这里要确认：
    * 行为只会被消费一次（前端每 2 秒轮询一次，绝不能每次都弹）；
    * 没有行为时字段是 `None` 而不是缺失（前端按字段判断）；
    * 互动后计时被重置。
"""

from datetime import datetime

import pytest

from app.interfaces.web.routes import pet as pet_route
from app.services.idle_service import IdleScheduler
from tests.test_web_cards import client as web_client  # noqa: F401  (pytest fixture)


@pytest.fixture
def fixed_scheduler():
    """把进程级调度器换成固定时钟的版本，测试结束后还原。"""
    original = pet_route._scheduler
    pet_route._scheduler = IdleScheduler(
        clock=lambda: datetime(2026, 1, 1, 9, 0),
        randomize=lambda: 0.0,
        greeting_delay=0,
        nudge_after=600,
        nudge_jitter=0,
    )
    yield pet_route._scheduler
    pet_route._scheduler = original


def test_state_includes_idle_action(web_client, fixed_scheduler):
    payload = web_client.get("/api/pet/state").json()["data"]
    action = payload["idle_action"]
    assert action is not None
    assert set(action) == {"kind", "text", "emotion"}
    assert action["kind"] == "greeting"
    assert action["text"]


def test_idle_action_is_consumed_once(web_client, fixed_scheduler):
    assert web_client.get("/api/pet/state").json()["data"]["idle_action"] is not None
    assert web_client.get("/api/pet/state").json()["data"]["idle_action"] is None
    assert web_client.get("/api/pet/state").json()["data"]["idle_action"] is None


def test_field_present_but_none_when_quiet(web_client, fixed_scheduler):
    web_client.get("/api/pet/state")  # 消费问候
    payload = web_client.get("/api/pet/state").json()["data"]
    assert "idle_action" in payload
    assert payload["idle_action"] is None


def test_touch_resets_idle_timer(web_client, fixed_scheduler):
    web_client.get("/api/pet/state")
    result = web_client.post("/api/pet/touch").json()["data"]
    assert result["touched"] is True
    assert result["state"]["idle_seconds"] == pytest.approx(0, abs=0.5)


def test_disabled_scheduler_returns_none(web_client):
    original = pet_route._scheduler
    pet_route._scheduler = IdleScheduler(enabled=False)
    try:
        assert web_client.get("/api/pet/state").json()["data"]["idle_action"] is None
    finally:
        pet_route._scheduler = original


def test_state_keeps_existing_fields(web_client, fixed_scheduler):
    """新增字段不能破坏原有契约（前端与 CLI 都在用）。"""
    payload = web_client.get("/api/pet/state").json()["data"]
    for field in ("emotion", "persona_name", "latest_message", "has_new_message", "timestamp"):
        assert field in payload
