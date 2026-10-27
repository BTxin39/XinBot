"""提醒与日程。

用途：久坐提醒、喝水、定时事项。设计上刻意**不做成闹钟**——
它通过桌宠气泡 + 语音提示，而不是弹窗抢焦点。

两个容易踩的坑，这里都用数据结构解决：
    1. **一次性提醒重复触发**：必须记 `fired`，否则每次轮询都会再响一次；
    2. **每日提醒同一天重复触发**：必须记 `last_fired_date`，
       而不是"今天已经过了 9:00 就一直算到期"。

时间全部走可注入的时钟，测试不需要 sleep，也不会因为跑测试的时间点不同而飘。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

REPEAT_ONCE = "once"
REPEAT_DAILY = "daily"
REPEATS = (REPEAT_ONCE, REPEAT_DAILY)

MAX_TEXT = 200


@dataclass
class Reminder:
    """一条提醒。

    `at` 的含义随 `repeat` 变化：
        once  → ISO 日期时间（"2026-05-01T09:00"）
        daily → "HH:MM"
    """

    text: str
    at: str
    repeat: str = REPEAT_ONCE
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    fired: bool = False
    last_fired_date: str = ""

    def normalized(self) -> "Reminder":
        repeat = self.repeat if self.repeat in REPEATS else REPEAT_ONCE
        return Reminder(
            text=str(self.text or "").strip()[:MAX_TEXT],
            at=str(self.at or "").strip(),
            repeat=repeat,
            enabled=bool(self.enabled),
            id=str(self.id or uuid.uuid4().hex[:8]),
            fired=bool(self.fired),
            last_fired_date=str(self.last_fired_date or ""),
        )


@dataclass
class DueReminder:
    id: str
    text: str
    repeat: str


def parse_daily(value: str) -> tuple[int, int] | None:
    """解析 "HH:MM"。非法返回 None（调用方负责报错）。"""
    try:
        hour_text, minute_text = value.strip().split(":")
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError):
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return hour, minute


def parse_once(value: str) -> datetime | None:
    """解析一次性提醒的时间。接受几种常见写法。"""
    text = (value or "").strip().replace("/", "-")
    if not text:
        return None
    for pattern in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def validate(text: str, at: str, repeat: str) -> str | None:
    """校验输入；返回错误信息，None 表示合法。"""
    if not (text or "").strip():
        return "提醒内容不能为空"
    if len(text.strip()) > MAX_TEXT:
        return f"提醒内容不能超过 {MAX_TEXT} 字"
    if repeat not in REPEATS:
        return "只支持 once（一次性）或 daily（每天）"
    if repeat == REPEAT_DAILY:
        if parse_daily(at) is None:
            return "每日提醒的时间格式应为 HH:MM，例如 09:30"
    else:
        if parse_once(at) is None:
            return "一次性提醒的时间格式应为 YYYY-MM-DDTHH:MM，例如 2026-05-01T09:00"
    return None


class ReminderBook:
    """提醒集合与到期判断。

    存储用注入的路径，测试不碰真实 `data/`。
    """

    def __init__(self, path=None, clock=None, randomize=None):
        self._path = path
        self._clock = clock or datetime.now
        self._random = randomize or (lambda: 0.0)
        self._items: list[Reminder] = []
        self._pending: list[DueReminder] = []
        self.load()

    # ── 持久化 ────────────────────────────────────────────────

    def load(self) -> None:
        self._items = []
        if self._path is None:
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, list):
            return
        known = set(Reminder.__dataclass_fields__)
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                self._items.append(
                    Reminder(**{k: v for k, v in entry.items() if k in known}).normalized()
                )
            except TypeError:
                continue

    def save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(item.normalized()) for item in self._items],
                             ensure_ascii=False, indent=2)
        temporary = self._path.with_suffix(".json.tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self._path)

    # ── 增删查 ────────────────────────────────────────────────

    def all(self) -> list[Reminder]:
        return list(self._items)

    def add(self, text: str, at: str, repeat: str = REPEAT_ONCE) -> Reminder:
        problem = validate(text, at, repeat)
        if problem:
            raise ValueError(problem)
        item = Reminder(text=text.strip(), at=at.strip(), repeat=repeat).normalized()
        self._items.append(item)
        self.save()
        return item

    def remove(self, reminder_id: str) -> bool:
        before = len(self._items)
        self._items = [item for item in self._items if item.id != reminder_id]
        if len(self._items) != before:
            self.save()
            return True
        return False

    def clear(self) -> int:
        count = len(self._items)
        self._items = []
        self._pending = []
        self.save()
        return count

    def toggle(self, reminder_id: str, enabled: bool) -> bool:
        for item in self._items:
            if item.id == reminder_id:
                item.enabled = bool(enabled)
                self.save()
                return True
        return False

    # ── 到期判断 ──────────────────────────────────────────────

    def due(self, now: datetime | None = None) -> list[Reminder]:
        """当前到期的提醒（不标记已触发）。"""
        moment = now or self._clock()
        result = []
        for item in self._items:
            if not item.enabled:
                continue
            if item.repeat == REPEAT_DAILY:
                parsed = parse_daily(item.at)
                if parsed is None:
                    continue
                hour, minute = parsed
                if (moment.hour, moment.minute) < (hour, minute):
                    continue
                # 今天已经提醒过就不再重复
                if item.last_fired_date == moment.date().isoformat():
                    continue
                result.append(item)
            else:
                if item.fired:
                    continue
                target = parse_once(item.at)
                if target is None or moment < target:
                    continue
                result.append(item)
        return result

    def take(self, now: datetime | None = None) -> DueReminder | None:
        """取一条到期提醒并标记为已触发。

        一次只取一条：桌宠每 2 秒轮询一次，一次吐出全部会把气泡刷爆。
        剩余的留到下一次轮询。
        """
        moment = now or self._clock()

        # 先把新到期的排进待发队列
        if not self._pending:
            for item in self.due(moment):
                self._pending.append(
                    DueReminder(id=item.id, text=item.text, repeat=item.repeat)
                )

        if not self._pending:
            return None

        reminder = self._pending.pop(0)
        self._mark_fired(reminder.id, moment)
        return reminder

    def _mark_fired(self, reminder_id: str, moment: datetime) -> None:
        changed = False
        for item in self._items:
            if item.id != reminder_id:
                continue
            if item.repeat == REPEAT_DAILY:
                item.last_fired_date = moment.date().isoformat()
            else:
                item.fired = True
            changed = True
        if changed:
            self.save()

    def reset_pending(self) -> None:
        self._pending.clear()

    def state(self) -> dict:
        moment = self._clock()
        return {
            "count": len(self._items),
            "enabled": sum(1 for item in self._items if item.enabled),
            "due": len(self.due(moment)),
            "now": moment.strftime("%Y-%m-%d %H:%M"),
        }


# 进程级单例
_book: ReminderBook | None = None


def book() -> ReminderBook:
    global _book
    if _book is None:
        from app.paths import repo_root

        _book = ReminderBook(path=repo_root() / "data" / "reminders.json")
    return _book


def reset_book(**kwargs) -> ReminderBook:
    global _book
    _book = ReminderBook(**kwargs)
    return _book
