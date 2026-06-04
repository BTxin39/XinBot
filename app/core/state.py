from dataclasses import dataclass


@dataclass
class Emotion:
    name: str
    description: str
    behavior_modifier: str


EMOTIONS: dict[str, Emotion] = {
    "normal": Emotion(
        name="normal",
        description="情绪平静",
        behavior_modifier="保持正常语气和节奏。",
    ),
    "happy": Emotion(
        name="happy",
        description="心情愉快",
        behavior_modifier="语气比平时更活泼，可以多用感叹号，更愿意主动开启话题。",
    ),
    "sad": Emotion(
        name="sad",
        description="有些失落",
        behavior_modifier="语气更轻柔，回复更简短，偶尔带一点忧郁的气息。",
    ),
    "angry": Emotion(
        name="angry",
        description="有点闹脾气",
        behavior_modifier="语气变得更不耐烦，但不要真的攻击用户。像在生闷气的样子。",
    ),
    "sleepy": Emotion(
        name="sleepy",
        description="很困",
        behavior_modifier="说话断断续续，打哈欠，反应慢半拍，随时可能睡着的样子。",
    ),
}


@dataclass
class AgentState:
    emotion: str = "normal"
    energy: int = 100
