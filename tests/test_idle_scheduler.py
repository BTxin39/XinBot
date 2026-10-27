"""待机行为调度的契约测试。

重点锁住"不会打扰用户"的性质：
    * 问候每次会话只出现一次；
    * 搭话有最小间隔，不会因为轮询频繁就反复弹；
    * 用户一互动就重新计时；
    * 深夜用更安静的表情。

时钟全部注入，测试不 sleep。
"""

from datetime import datetime, timedelta

import pytest

from app.services.idle_service import (
    IdleAction,
    IdleScheduler,
    bucket_for,
)


class FakeClock:
    def __init__(self, moment: datetime):
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **kwargs) -> None:
        self.moment += timedelta(**kwargs)


def scheduler_at(moment: datetime, **kwargs) -> tuple[IdleScheduler, FakeClock]:
    clock = FakeClock(moment)
    # 固定随机数，保证文案与间隔可预测
    return IdleScheduler(clock=clock, randomize=lambda: 0.0, **kwargs), clock


# ── 时段划分 ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "hour,expected",
    [
        (5, "morning"), (9, "morning"),
        (10, "noon"), (13, "noon"),
        (14, "afternoon"), (17, "afternoon"),
        (18, "evening"), (22, "evening"),
        (23, "night"), (0, "night"), (4, "night"),
    ],
)
def test_bucket_boundaries(hour, expected):
    assert bucket_for(hour) == expected


def test_bucket_handles_out_of_range_hours():
    assert bucket_for(25) == bucket_for(1)
    assert bucket_for(-1) == bucket_for(23)


# ── 问候 ──────────────────────────────────────────────────────────

def test_greets_once_per_session():
    scheduler, _ = scheduler_at(datetime(2026, 1, 1, 9, 0))
    first = scheduler.poll()
    assert first is not None and first.kind == "greeting"
    assert first.bucket == "morning"
    # 同一时段内不再重复问候
    assert scheduler.poll() is None


def test_greeting_changes_when_bucket_changes():
    """长时间挂着（跨时段）时，换时段应该再问候一次。"""
    scheduler, clock = scheduler_at(datetime(2026, 1, 1, 9, 0))
    assert scheduler.poll().bucket == "morning"
    clock.advance(hours=3)  # 12:00 → noon
    action = scheduler.poll()
    assert action is not None and action.bucket == "noon"


def test_greeting_delay_defers_first_greeting():
    """给页面的加载留一点时间，别一启动就弹。"""
    scheduler, clock = scheduler_at(datetime(2026, 1, 1, 9, 0), greeting_delay=5)
    assert scheduler.poll() is None
    clock.advance(seconds=6)
    assert scheduler.poll().kind == "greeting"


def test_night_greeting_is_calm():
    scheduler, _ = scheduler_at(datetime(2026, 1, 1, 23, 30))
    action = scheduler.poll()
    assert action.bucket == "night"
    assert action.emotion == "normal"


# ── 静默搭话 ──────────────────────────────────────────────────────

def test_no_nudge_before_interval():
    scheduler, clock = scheduler_at(datetime(2026, 1, 1, 9, 0), nudge_after=600, nudge_jitter=0)
    scheduler.poll()  # 消费掉问候
    clock.advance(seconds=599)
    assert scheduler.poll() is None


def test_nudge_after_interval():
    scheduler, clock = scheduler_at(datetime(2026, 1, 1, 9, 0), nudge_after=600, nudge_jitter=0)
    scheduler.poll()
    clock.advance(seconds=601)
    action = scheduler.poll()
    assert action is not None and action.kind == "nudge"


def test_nudges_are_spaced_out():
    """两条搭话之间必须满足最小间隔，否则轮询会连环弹。"""
    scheduler, clock = scheduler_at(datetime(2026, 1, 1, 9, 0), nudge_after=600, nudge_jitter=0)
    scheduler.poll()
    clock.advance(seconds=601)
    assert scheduler.poll().kind == "nudge"
    # 立刻再轮询：不该又来一条
    clock.advance(seconds=10)
    assert scheduler.poll() is None
    clock.advance(seconds=600)
    assert scheduler.poll().kind == "nudge"


def test_interaction_resets_idle_timer():
    scheduler, clock = scheduler_at(datetime(2026, 1, 1, 9, 0), nudge_after=600, nudge_jitter=0)
    scheduler.poll()
    clock.advance(seconds=500)
    scheduler.touch()
    clock.advance(seconds=500)
    assert scheduler.poll() is None, "刚互动过就不该搭话"


def test_night_nudge_uses_sleepy_emotion():
    scheduler, clock = scheduler_at(datetime(2026, 1, 1, 23, 10), nudge_after=60, nudge_jitter=0)
    scheduler.poll()  # 消费问候
    clock.advance(minutes=2)
    action = scheduler.poll()
    assert action.kind == "nudge"
    assert action.emotion == "sleepy", "深夜劝睡应该用安静的表情"


# ── 开关与状态 ────────────────────────────────────────────────────

def test_disabled_scheduler_is_silent():
    scheduler, clock = scheduler_at(datetime(2026, 1, 1, 9, 0), enabled=False)
    clock.advance(hours=2)
    assert scheduler.poll() is None
    assert scheduler.state()["enabled"] is False


def test_state_reports_progress():
    scheduler, clock = scheduler_at(datetime(2026, 1, 1, 9, 0))
    assert scheduler.state()["greeted"] is False
    scheduler.poll()
    clock.advance(seconds=30)
    state = scheduler.state()
    assert state["greeted"] is True
    assert state["bucket"] == "morning"
    assert state["idle_seconds"] == pytest.approx(30, abs=0.5)


def test_action_is_immutable():
    action = IdleAction(kind="greeting", text="hi")
    with pytest.raises(Exception):
        action.text = "changed"  # frozen dataclass


def test_text_pools_cover_every_bucket():
    """每个时段都必须有文案，否则会 KeyError 崩在轮询里。"""
    from app.services.idle_service import GREETINGS, NUDGES, TIME_BUCKETS

    for _start, _end, bucket in TIME_BUCKETS:
        assert GREETINGS.get(bucket), f"{bucket} 缺少问候语"
        assert NUDGES.get(bucket), f"{bucket} 缺少搭话语"
