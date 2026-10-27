"""点击 / 拖拽反应的契约测试。

三条性质必须成立：
    1. **冷却生效** —— 用户狂点不该刷屏；
    2. **动作组有兜底** —— 不同模型的动作组名不一样，最后一项必须是空字符串
       （pixi-live2d-display 里表示"随便挑一个"），否则某些模型会完全没反应；
    3. **未知输入不炸** —— 未知 kind 返回 None，未知情绪回落 normal。
"""

import pytest

from app.services.interaction_service import (
    BUBBLES,
    COOLDOWNS,
    MOTION_CANDIDATES,
    SUPPORTED_KINDS,
    InteractionPlanner,
    Reaction,
)


class Clock:
    def __init__(self, value: int = 0):
        self.value = value

    def __call__(self) -> int:
        return self.value

    def advance(self, ms: int) -> None:
        self.value += ms


def make_planner(**kwargs):
    clock = Clock()
    planner = InteractionPlanner(clock=clock, randomize=lambda: 0.0, **kwargs)
    return planner, clock


# ── 基本反应 ──────────────────────────────────────────────────────

def test_tap_returns_reaction():
    planner, _ = make_planner()
    reaction = planner.plan("tap", "normal")
    assert reaction is not None
    assert reaction.kind == "tap"
    assert reaction.bubble
    assert reaction.motions
    assert reaction.cooldown_ms == COOLDOWNS["tap"]


@pytest.mark.parametrize("kind", SUPPORTED_KINDS)
def test_every_kind_has_reaction(kind):
    planner, _ = make_planner()
    reaction = planner.plan(kind, "normal")
    assert reaction is not None, f"{kind} 应当有反应"
    assert reaction.bubble
    assert reaction.motions


def test_every_kind_has_bubbles_for_all_emotions():
    """情绪缺失会导致 KeyError 变成 500，必须每个组合都有文案。"""
    emotions = {"normal", "happy", "sad", "angry", "sleepy"}
    for kind in SUPPORTED_KINDS:
        pools = BUBBLES[kind]
        for emotion in emotions:
            assert pools.get(emotion), f"{kind}/{emotion} 缺少文案"


# ── 冷却 ──────────────────────────────────────────────────────────

def test_cooldown_blocks_rapid_taps():
    planner, clock = make_planner()
    assert planner.plan("tap") is not None
    clock.advance(100)
    assert planner.plan("tap") is None, "冷却期内不该再反应"
    clock.advance(COOLDOWNS["tap"])
    assert planner.plan("tap") is not None


def test_cooldowns_are_independent_per_kind():
    """点一下再拖一下，不该互相压制。"""
    planner, clock = make_planner()
    assert planner.plan("tap") is not None
    clock.advance(10)
    assert planner.plan("drag_start") is not None


def test_reaction_after_full_cooldown():
    planner, clock = make_planner()
    planner.plan("drop")
    clock.advance(COOLDOWNS["drop"] - 1)
    assert planner.plan("drop") is None
    clock.advance(1)
    assert planner.plan("drop") is not None


def test_reset_clears_cooldowns():
    planner, _clock = make_planner()
    assert planner.plan("tap") is not None
    assert planner.plan("tap") is None
    planner.reset()
    assert planner.plan("tap") is not None


# ── 动作组兜底 ────────────────────────────────────────────────────

def test_tap_motions_fall_back_to_empty_group():
    """最后一项必须是空字符串，否则没有 TapBody 的模型会一动不动。"""
    assert MOTION_CANDIDATES["tap"][-1] == ""
    assert MOTION_CANDIDATES["drop"][-1] == ""


def test_motion_candidates_prefer_named_groups():
    for kind, groups in MOTION_CANDIDATES.items():
        assert groups[0], f"{kind} 应当优先尝试具名动作组"
        assert kind in SUPPORTED_KINDS


# ── 健壮性 ────────────────────────────────────────────────────────

def test_unknown_kind_is_ignored():
    planner, _ = make_planner()
    assert planner.plan("explode") is None


def test_unknown_emotion_falls_back_to_normal():
    planner, _ = make_planner()
    reaction = planner.plan("tap", "furious")
    assert reaction is not None
    assert reaction.bubble in BUBBLES["tap"]["normal"]


def test_reaction_is_immutable():
    reaction = Reaction(kind="tap", bubble="hi", emotion="normal")
    with pytest.raises(Exception):
        reaction.bubble = "changed"


def test_state_lists_supported_kinds():
    planner, _ = make_planner()
    state = planner.state()
    assert set(state["supported"]) == set(SUPPORTED_KINDS)
    assert state["cooldowns"] == COOLDOWNS


def test_emotion_varies_bubble():
    """不同情绪应当给出不同文案（而不是永远同一句）。"""
    happy = InteractionPlanner(clock=Clock(), randomize=lambda: 0.0).plan("tap", "happy")
    angry = InteractionPlanner(clock=Clock(), randomize=lambda: 0.0).plan("tap", "angry")
    assert happy.bubble != angry.bubble
