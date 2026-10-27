"""提醒服务的契约测试。

重点是"不要重复打扰"：
    * 一次性提醒触发后必须彻底停止（`fired`）；
    * 每日提醒同一天只响一次（`last_fired_date`，而不是"过了点就一直到期"）；
    * 一次轮询只吐一条，避免气泡刷屏。

时钟全部注入，测试不 sleep，也不受运行时刻影响。
"""

import json
from datetime import datetime

import pytest

from app.services.reminder_service import (
    REPEAT_DAILY,
    REPEAT_ONCE,
    ReminderBook,
    parse_daily,
    parse_once,
    validate,
)


class Clock:
    def __init__(self, moment: datetime):
        self.moment = moment

    def __call__(self):
        return self.moment


def make_book(tmp_path, moment, name="reminders.json"):
    clock = Clock(moment)
    return ReminderBook(path=tmp_path / "data" / name, clock=clock), clock


# ── 解析与校验 ────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("09:30", (9, 30)),
    ("0:00", (0, 0)),
    ("23:59", (23, 59)),
    ("24:00", None),
    ("9", None),
    ("9:70", None),
    ("", None),
    ("abc", None),
])
def test_parse_daily(value, expected):
    assert parse_daily(value) == expected


@pytest.mark.parametrize("value", [
    "2026-05-01T09:00",
    "2026-05-01 09:00",
    "2026-05-01T09:00:30",
    "2026/05/01 09:00",
])
def test_parse_once_accepts_common_formats(value):
    parsed = parse_once(value)
    assert parsed is not None
    assert parsed.year == 2026 and parsed.month == 5


def test_validate_rejects_empty_text():
    assert validate("  ", "09:00", REPEAT_DAILY)


def test_validate_rejects_bad_time_for_repeat():
    assert validate("喝水", "9点", REPEAT_DAILY)
    assert validate("喝水", "09:00", REPEAT_ONCE)


def test_validate_accepts_valid_input():
    assert validate("喝水", "09:00", REPEAT_DAILY) is None
    assert validate("开会", "2026-05-01T09:00", REPEAT_ONCE) is None


# ── 增删查 ────────────────────────────────────────────────────────

def test_add_and_persist(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 8, 0))
    item = book.add("喝水", "09:00", REPEAT_DAILY)
    assert item.text == "喝水"
    saved = json.loads((tmp_path / "data" / "reminders.json").read_text(encoding="utf-8"))
    assert saved[0]["text"] == "喝水"
    assert saved[0]["repeat"] == REPEAT_DAILY


def test_add_rejects_invalid(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 8, 0))
    with pytest.raises(ValueError):
        book.add("", "09:00", REPEAT_DAILY)


def test_remove_and_clear(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 8, 0))
    first = book.add("a", "09:00", REPEAT_DAILY)
    book.add("b", "10:00", REPEAT_DAILY)
    assert book.remove(first.id) is True
    assert book.remove("nope") is False
    assert len(book.all()) == 1
    assert book.clear() == 1
    assert book.all() == []


def test_toggle_enables_and_disables(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 8, 0))
    item = book.add("喝水", "09:00", REPEAT_DAILY)
    assert book.toggle(item.id, False) is True
    assert book.all()[0].enabled is False
    assert book.due(datetime(2026, 5, 1, 10, 0)) == []


def test_corrupt_file_is_tolerated(tmp_path):
    path = tmp_path / "data" / "reminders.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    book = ReminderBook(path=path)
    assert book.all() == []


# ── 到期与"不重复打扰" ────────────────────────────────────────────

def test_daily_not_due_before_time(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 8, 0))
    book.add("喝水", "09:00", REPEAT_DAILY)
    assert book.due(datetime(2026, 5, 1, 8, 59)) == []


def test_daily_due_at_time(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 8, 0))
    book.add("喝水", "09:00", REPEAT_DAILY)
    assert len(book.due(datetime(2026, 5, 1, 9, 0))) == 1


def test_daily_fires_only_once_per_day(tmp_path):
    """过了点不等于一直到期——这是最容易写错的地方。"""
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 9, 0))
    book.add("喝水", "09:00", REPEAT_DAILY)
    assert book.take(datetime(2026, 5, 1, 9, 0)) is not None
    # 同一分钟内再轮询
    assert book.take(datetime(2026, 5, 1, 9, 1)) is None
    # 同一天晚些时候
    assert book.take(datetime(2026, 5, 1, 15, 0)) is None
    # 第二天同一时间又该提醒
    assert book.take(datetime(2026, 5, 2, 9, 0)) is not None


def test_once_fires_once_ever(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 8, 0))
    book.add("开会", "2026-05-01T09:00", REPEAT_ONCE)
    assert book.take(datetime(2026, 5, 1, 9, 0)) is not None
    assert book.take(datetime(2026, 5, 1, 9, 30)) is None
    # 隔几天也不会再响
    assert book.take(datetime(2026, 5, 5, 9, 0)) is None


def test_once_not_due_before_target(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 8, 0))
    book.add("开会", "2026-05-01T09:00", REPEAT_ONCE)
    assert book.take(datetime(2026, 5, 1, 8, 30)) is None


def test_take_returns_one_at_a_time(tmp_path):
    """一次只吐一条：桌宠每 2 秒轮询，全吐出来会刷屏。"""
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 9, 0))
    book.add("a", "09:00", REPEAT_DAILY)
    book.add("b", "09:00", REPEAT_DAILY)
    first = book.take(datetime(2026, 5, 1, 9, 0))
    second = book.take(datetime(2026, 5, 1, 9, 0))
    third = book.take(datetime(2026, 5, 1, 9, 0))
    assert first is not None and second is not None
    assert first.text != second.text
    assert third is None


def test_disabled_reminder_never_fires(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 9, 0))
    item = book.add("喝水", "09:00", REPEAT_DAILY)
    book.toggle(item.id, False)
    assert book.take(datetime(2026, 5, 1, 9, 0)) is None


def test_fired_state_persists(tmp_path):
    """重启后不能把已经响过的一次性提醒再响一遍。"""
    path = tmp_path / "data" / "reminders.json"
    clock = Clock(datetime(2026, 5, 1, 9, 0))
    book = ReminderBook(path=path, clock=clock)
    book.add("开会", "2026-05-01T09:00", REPEAT_ONCE)
    assert book.take(datetime(2026, 5, 1, 9, 0)) is not None

    reloaded = ReminderBook(path=path, clock=clock)
    assert reloaded.take(datetime(2026, 5, 1, 9, 5)) is None


def test_daily_last_fired_date_persists(tmp_path):
    path = tmp_path / "data" / "reminders.json"
    clock = Clock(datetime(2026, 5, 1, 9, 0))
    book = ReminderBook(path=path, clock=clock)
    book.add("喝水", "09:00", REPEAT_DAILY)
    assert book.take(datetime(2026, 5, 1, 9, 0)) is not None

    reloaded = ReminderBook(path=path, clock=clock)
    assert reloaded.take(datetime(2026, 5, 1, 12, 0)) is None


def test_state_reports_counts(tmp_path):
    book, _ = make_book(tmp_path, datetime(2026, 5, 1, 9, 0))
    book.add("a", "09:00", REPEAT_DAILY)
    book.add("b", "23:00", REPEAT_DAILY)
    state = book.state()
    assert state["count"] == 2
    assert state["enabled"] == 2
    assert state["due"] == 1
    assert state["now"].startswith("2026-05-01")
