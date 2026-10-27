"""`/api/pet/interact` 的接口契约。

冷却在服务端做，所以这里要确认：
    * 冷却期内返回 `reaction: null`（而不是错误）；
    * 不同 kind 的冷却互不影响；
    * 任何互动都会重置待机计时。
"""

import pytest

from app.interfaces.web.routes import pet as pet_route
from app.services.interaction_service import InteractionPlanner
from app.services.idle_service import IdleScheduler
from tests.test_web_cards import client as web_client  # noqa: F401  (pytest fixture)


class Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value

    def advance(self, ms):
        self.value += ms


@pytest.fixture
def planner_clock():
    clock = Clock()
    original = pet_route._planner
    pet_route._planner = InteractionPlanner(clock=clock, randomize=lambda: 0.0)
    yield clock
    pet_route._planner = original


def test_tap_returns_reaction(web_client, planner_clock):
    payload = web_client.post("/api/pet/interact", json={"kind": "tap", "emotion": "happy"}).json()
    reaction = payload["data"]["reaction"]
    assert reaction["kind"] == "tap"
    assert reaction["bubble"]
    assert reaction["motions"]
    assert reaction["cooldown_ms"] > 0


def test_cooldown_returns_null_not_error(web_client, planner_clock):
    first = web_client.post("/api/pet/interact", json={"kind": "tap"}).json()
    assert first["data"]["reaction"] is not None
    second = web_client.post("/api/pet/interact", json={"kind": "tap"}).json()
    assert second["ok"] is True, "冷却不该变成错误"
    assert second["data"]["reaction"] is None


def test_cooldown_expires(web_client, planner_clock):
    first = web_client.post("/api/pet/interact", json={"kind": "tap"}).json()
    cooldown = first["data"]["reaction"]["cooldown_ms"]
    planner_clock.advance(cooldown)
    assert web_client.post("/api/pet/interact", json={"kind": "tap"}).json()["data"]["reaction"]


def test_kinds_do_not_share_cooldown(web_client, planner_clock):
    web_client.post("/api/pet/interact", json={"kind": "tap"})
    payload = web_client.post("/api/pet/interact", json={"kind": "drop"}).json()
    assert payload["data"]["reaction"]["kind"] == "drop"


def test_unknown_kind_is_ignored(web_client, planner_clock):
    payload = web_client.post("/api/pet/interact", json={"kind": "explode"}).json()
    assert payload["ok"] is True
    assert payload["data"]["reaction"] is None


def test_unknown_emotion_falls_back(web_client, planner_clock):
    payload = web_client.post("/api/pet/interact", json={"kind": "tap", "emotion": "furious"}).json()
    assert payload["data"]["reaction"] is not None


def test_interaction_resets_idle_timer(web_client, planner_clock):
    """点一下桌宠就不该马上被"搭话"。"""
    original = pet_route._scheduler
    pet_route._scheduler = IdleScheduler(greeting_delay=0, nudge_after=0, nudge_jitter=0)
    try:
        web_client.get("/api/pet/state")  # 消费问候
        web_client.post("/api/pet/interact", json={"kind": "tap"})
        state = pet_route._scheduler.state()
        assert state["idle_seconds"] == pytest.approx(0, abs=0.5)
    finally:
        pet_route._scheduler = original


def test_oversized_kind_is_rejected(web_client):
    response = web_client.post("/api/pet/interact", json={"kind": "x" * 100})
    assert response.status_code == 422
