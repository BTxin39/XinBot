"""点击/拖拽反应。

为什么把"反应决策"放在后端：
    * 冷却、文案、表情映射都是规则，散落在 Vue 里既难测也难复用；
    * 将来 CLI 与桌宠壳都要用同一套反应；
    * 前端只负责"把动作放出去"，不做判断。

模型差异的现实：每个 Live2D 模型的**动作组名各不相同**
（`TapBody` / `tap_body` / 空组都有），所以这里返回**候选列表**，
前端按顺序尝试，第一个存在且能播放的生效。这样不用为每个模型写适配代码。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# 各种互动对应的动作组候选（按优先级）。空字符串是 pixi-live2d-display 里
# "随便挑一个动作组"的写法，作为最后的兜底。
MOTION_CANDIDATES: dict[str, tuple[str, ...]] = {
    "tap": ("TapBody", "tap_body", "tap", ""),
    "double_tap": ("TapHead", "tap_head", "TapBody", ""),
    "drag_start": ("Pinched", "pinched", "TapBody"),
    "drop": ("Flick", "flick", "TapBody", ""),
}

# 互动文案：按当前情绪挑，避免"生气时还在卖萌"这种违和。
BUBBLES: dict[str, dict[str, tuple[str, ...]]] = {
    "tap": {
        "happy": ("嘿嘿～", "被你摸到了！", "好开心！"),
        "angry": ("别戳啦！", "哼，再戳就生气了。"),
        "sad": ("嗯…？", "陪陪我吧。"),
        "sleepy": ("唔…好困…", "让我再睡会儿…"),
        "normal": ("诶？", "怎么了？", "在呢在呢。"),
    },
    "double_tap": {
        "happy": ("两次哦！", "这么喜欢我呀？"),
        "angry": ("都说了别戳！",),
        "sad": ("我在的…",),
        "sleepy": ("唔…别晃…",),
        "normal": ("摸头？", "有什么事吗？"),
    },
    "drag_start": {
        "normal": ("哇——", "要带我去哪？"),
        "happy": ("起飞！",),
        "sleepy": ("唔…搬我吗…",),
        "angry": ("放我下来！",),
        "sad": ("…哦。",),
    },
    "drop": {
        "normal": ("安全着陆～", "站稳了！"),
        "happy": ("再来一次！",),
        "sleepy": ("…落地了。",),
        "angry": ("你就不能轻点吗。",),
        "sad": ("…嗯。",),
    },
}

# 每种互动的冷却（毫秒）。防连点刷屏——用户狂点不该刷出 20 条气泡。
COOLDOWNS: dict[str, int] = {
    "tap": 700,
    "double_tap": 900,
    "drag_start": 1500,
    "drop": 500,
}

# 互动时切换到的表情（索引），None 表示交给模型自己随机
EMOTIONS: dict[str, str] = {
    "tap": "happy",
    "double_tap": "happy",
    "drag_start": "normal",
    "drop": "happy",
}

SUPPORTED_KINDS = tuple(MOTION_CANDIDATES)


@dataclass(frozen=True)
class Reaction:
    """一次互动的反应。前端照着执行即可。"""

    kind: str
    bubble: str
    emotion: str
    motions: tuple[str, ...] = field(default_factory=tuple)
    expression: int | None = None
    cooldown_ms: int = 0


class InteractionPlanner:
    """按冷却与情绪决定"这次互动该有什么反应"。

    时钟与随机源可注入，测试不需要 sleep，也不需要真实模型。
    """

    def __init__(self, clock=None, randomize=None):
        # clock 返回**毫秒**时间戳，方便和前端的时间对齐
        self._clock = clock or (lambda: int(__import__("time").monotonic() * 1000))
        self._random = randomize or random.random
        self._last: dict[str, int] = {}

    def plan(self, kind: str, emotion: str = "normal") -> Reaction | None:
        """返回反应；冷却中或未知类型返回 None。"""
        if kind not in SUPPORTED_KINDS:
            return None

        now = self._clock()
        cooldown = COOLDOWNS[kind]
        last = self._last.get(kind)
        if last is not None and now - last < cooldown:
            return None
        self._last[kind] = now

        # 未知情绪回落到 normal，避免 KeyError 让接口 500
        pools = BUBBLES.get(kind, {})
        pool = pools.get(emotion) or pools.get("normal") or ("嗯？",)
        bubble = pool[int(self._random() * len(pool)) % len(pool)]

        return Reaction(
            kind=kind,
            bubble=bubble,
            emotion=EMOTIONS.get(kind, "normal"),
            motions=MOTION_CANDIDATES[kind],
            expression=None,
            cooldown_ms=cooldown,
        )

    def reset(self) -> None:
        self._last.clear()

    def state(self) -> dict:
        return {"supported": list(SUPPORTED_KINDS), "cooldowns": dict(COOLDOWNS)}
