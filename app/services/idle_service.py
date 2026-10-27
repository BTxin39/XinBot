"""待机行为调度：让桌宠"活着"，而不是一个挂着的静态立绘。

设计原则：
    * **纯逻辑 + 可注入时钟/随机源** —— 行为取决于"过了多久"，若直接读
      `time.time()` 就只能靠 `sleep` 测，既慢又不稳；
    * **懒计算**：不额外起后台线程，每次轮询时判断一次是否该触发，
      触发后立即记录，保证同一条只会出现一次；
    * **按会话而非按天计**：重启后重新问候一次是合理体验，
      但如果用户连续用几天不重启，也不该反复问"早上好"。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

# 时段划分（小时，左闭右开）。深夜单独拎出来，因为它要影响"劝睡"行为。
TIME_BUCKETS: tuple[tuple[int, int, str], ...] = (
    (5, 10, "morning"),
    (10, 14, "noon"),
    (14, 18, "afternoon"),
    (18, 23, "evening"),
    (23, 24, "night"),
    (0, 5, "night"),
)

def _buckets() -> list[str]:
    return [name for _start, _end, name in TIME_BUCKETS]


def pools(locale: str | None = None) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """按语言取问候语与搭话池。

    文案放在 i18n_service.MESSAGES 里统一管理，这里只按 <用途>.<时段> 取键，
    避免同一个时段在多个地方各写一份。
    """
    from app.services import i18n_service

    greetings = {
        bucket: i18n_service.t_list(f"idle.greeting.{bucket}", locale)
        for bucket in _buckets()
    }
    nudges = {
        bucket: i18n_service.t_list(f"idle.nudge.{bucket}", locale)
        for bucket in _buckets()
    }
    return greetings, nudges


# 兼容旧调用点：模块级常量取默认语言（中文）
GREETINGS, NUDGES = pools()

@dataclass(frozen=True)
class IdleAction:
    """一次待机行为。前端据此改气泡与表情。"""

    kind: str  # greeting | nudge
    text: str
    emotion: str = "normal"
    bucket: str = "noon"


def bucket_for(hour: int) -> str:
    """把小时映射到时段名。"""
    hour = int(hour) % 24
    for start, end, name in TIME_BUCKETS:
        if start <= hour < end:
            return name
    return "noon"


class IdleScheduler:
    """决定"现在要不要主动说点什么"。

    参数都可在测试里注入：
        clock       —— 返回 `datetime` 的函数（默认 `datetime.now`）
        randomize   —— 返回 0.0~1.0 的函数（默认 `random.random`）
        nudge_after —— 静默多久后开始考虑搭话（秒）
    """

    def __init__(
        self,
        clock=None,
        randomize=None,
        *,
        nudge_after: float = 25 * 60,
        nudge_jitter: float = 8 * 60,
        greeting_delay: float = 0.0,
        enabled: bool = True,
        locale: str | None = None,
    ):
        self._clock = clock or datetime.now
        self._random = randomize or random.random
        self._nudge_after = float(nudge_after)
        self._nudge_jitter = float(nudge_jitter)
        self._greeting_delay = float(greeting_delay)
        self.enabled = enabled
        # 语言在构造时固定：运行中切换语言需要重建调度器，
        # 否则会出现"问候中文、搭话英文"的混搭
        self.locale = locale
        self._greetings, self._nudges = pools(locale)

        now = self._now()
        self._started_at = now
        self._last_interaction = now
        self._last_nudge: datetime | None = None
        self._greeted_bucket: str | None = None
        self._next_nudge_gap = self._pick_gap()

    # ── 对外 ──────────────────────────────────────────────────

    def touch(self) -> None:
        """用户与桌宠有互动：重新计时，并且允许之后再次问候。"""
        self._last_interaction = self._now()
        self._last_nudge = None
        self._next_nudge_gap = self._pick_gap()

    def poll(self) -> IdleAction | None:
        """返回本次应当触发的行为；没有就返回 None。

        调用一次即视为"消费掉"该行为，重复调用不会重复返回。
        """
        if not self.enabled:
            return None

        now = self._now()
        bucket = bucket_for(now.hour)

        # 1) 启动问候：每次会话每个时段最多一次
        if self._greeted_bucket != bucket:
            if (now - self._started_at).total_seconds() >= self._greeting_delay:
                self._greeted_bucket = bucket
                return IdleAction(
                    kind="greeting",
                    text=self._pick(self._greetings[bucket] or ["…"]),
                    emotion="happy" if bucket in ("morning", "noon") else "normal",
                    bucket=bucket,
                )

        # 2) 静默搭话：距上次互动超过间隔才考虑，且两条之间有最小间隔
        idle_seconds = (now - self._last_interaction).total_seconds()
        if idle_seconds >= self._nudge_after:
            if self._last_nudge is None or (
                now - self._last_nudge
            ).total_seconds() >= self._next_nudge_gap:
                self._last_nudge = now
                self._next_nudge_gap = self._pick_gap()
                return IdleAction(
                    kind="nudge",
                    text=self._pick(self._nudges[bucket] or ["…"]),
                    # 深夜劝睡用一个更"安静"的表情，别把用户吵精神了
                    emotion="sleepy" if bucket == "night" else "normal",
                    bucket=bucket,
                )

        return None

    def state(self) -> dict:
        """调试/接口用：当前调度状态（不含文案）。"""
        now = self._now()
        return {
            "enabled": self.enabled,
            "locale": self.locale,
            "bucket": bucket_for(now.hour),
            "idle_seconds": round((now - self._last_interaction).total_seconds(), 1),
            "nudge_after": self._nudge_after,
            "greeted": self._greeted_bucket is not None,
        }

    # ── 内部 ──────────────────────────────────────────────────

    def _now(self) -> datetime:
        return self._clock()

    def _pick(self, pool: list[str]) -> str:
        index = int(self._random() * len(pool)) % len(pool)
        return pool[index]

    def _pick_gap(self) -> float:
        """下一次搭话的最小间隔：基础值 + 随机抖动，避免每次都是整点。"""
        return self._nudge_after + self._random() * self._nudge_jitter
