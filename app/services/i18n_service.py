"""多语言（i18n）。

范围说明（刻意的取舍）：
    第一版只覆盖**两类文本**——
      1. 后端产生、直接展示给用户的字符串（待机问候/搭话、工具轮次上限提示等）；
      2. 前端高频界面（导航、页头、按钮）。
    角色卡内容、聊天记录、文档不在范围内：那些是**用户数据或文档**，
    机器翻译只会让体验更差。

设计：
    * 语言代码用 BCP 47 子集（`zh-CN` / `en`）；
    * 未知语言**回落默认**而不是报错（配置写错不该白屏）；
    * 缺失键回落默认语言，再退回键名本身（便于发现漏翻）。
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_LOCALE = "zh-CN"

# 语言显示名（给前端下拉用）
LOCALES: dict[str, str] = {
    "zh-CN": "简体中文",
    "en": "English",
}

# 服务端文案。键用小写点分，便于对照。
MESSAGES: dict[str, dict[str, object]] = {
    "zh-CN": {
        "agent.max_iterations": "（已达到最大工具调用次数，请重新输入。）",
        "idle.greeting.morning": [
            "早上好呀，今天也要打起精神哦！",
            "早安～ 新的一天开始啦。",
        ],
        "idle.greeting.noon": ["中午好，记得吃饭哦。", "到饭点了，别只顾着忙。"],
        "idle.greeting.afternoon": ["下午好，来杯水休息一下吧。", "又见面啦，有什么想聊的吗？"],
        "idle.greeting.evening": ["晚上好，今天过得怎么样？", "辛苦一天啦，晚上想聊点什么？"],
        "idle.greeting.night": ["这么晚还没睡呀？", "夜深了，早点休息哦。"],
        "idle.nudge.morning": ["已经坐了好一会儿了，站起来伸个懒腰？", "眼睛要不要休息一下？"],
        "idle.nudge.noon": ["要不要先吃点东西？", "喝口水吧，我陪你。"],
        "idle.nudge.afternoon": ["盯屏幕太久啦，看看远处。", "保持这个姿势有点久了哦。"],
        "idle.nudge.evening": ["今天还顺利吗？", "要不要聊两句放松一下？"],
        "idle.nudge.night": ["该准备睡了哦。", "明天还要早起的话，现在就收工吧。"],
    },
    "en": {
        "agent.max_iterations": "(Maximum tool calls reached. Please try again.)",
        "idle.greeting.morning": [
            "Good morning! Let's make today count.",
            "Morning — a brand new day starts now.",
        ],
        "idle.greeting.noon": ["Good afternoon. Don't forget lunch!", "It's lunchtime — take a break."],
        "idle.greeting.afternoon": ["Good afternoon. Want some water?", "We meet again — anything on your mind?"],
        "idle.greeting.evening": ["Good evening. How was your day?", "Long day? Want to chat a bit?"],
        "idle.greeting.night": ["Still up this late?", "It's late — get some rest."],
        "idle.nudge.morning": ["You've been sitting a while — stretch?", "Let your eyes rest for a moment."],
        "idle.nudge.noon": ["Maybe grab something to eat first?", "Drink some water — I'll wait."],
        "idle.nudge.afternoon": ["Too long in front of the screen — look far away.", "You've held that posture a while."],
        "idle.nudge.evening": ["Did today go well?", "Want to relax and chat for a bit?"],
        "idle.nudge.night": ["Time to wind down.", "If tomorrow starts early, call it a night."],
    },
}


def normalize(locale: str | None) -> str:
    """把任意输入收敛成受支持的语言代码。

    接受 `en-US` → `en`（去掉地区），未知一律回落默认语言。
    """
    value = (locale or "").strip().replace("_", "-")
    if not value:
        return DEFAULT_LOCALE
    if value in LOCALES:
        return value
    base = value.split("-")[0].lower()
    if base == "zh":
        return "zh-CN"
    if base in LOCALES:
        return base
    return DEFAULT_LOCALE


def t(key: str, locale: str | None = None, **kwargs) -> str:
    """取一条文案；缺失时依次回落：目标语言 → 默认语言 → 键名。"""
    resolved = normalize(locale)
    value = MESSAGES.get(resolved, {}).get(key)
    if value is None:
        value = MESSAGES[DEFAULT_LOCALE].get(key)
    if value is None:
        return key
    text = str(value)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def t_list(key: str, locale: str | None = None) -> list[str]:
    """取一组文案（问候语池等）；不是列表时回退成单元素列表。"""
    resolved = normalize(locale)
    value = MESSAGES.get(resolved, {}).get(key)
    if value is None:
        value = MESSAGES[DEFAULT_LOCALE].get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def catalog(locale: str | None = None) -> dict:
    """给前端的整包文案（未翻译的键会以默认语言补齐）。"""
    resolved = normalize(locale)
    merged = dict(MESSAGES[DEFAULT_LOCALE])
    merged.update(MESSAGES.get(resolved, {}))
    return merged


def available() -> list[dict]:
    return [{"code": code, "label": label} for code, label in LOCALES.items()]


# ── 持久化 ────────────────────────────────────────────────────────

def settings_path(root: Path) -> Path:
    return Path(root) / "data" / "locale.json"


def load(root: Path) -> str:
    path = settings_path(root)
    if not path.is_file():
        return DEFAULT_LOCALE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_LOCALE
    if isinstance(raw, dict):
        return normalize(str(raw.get("locale", "")))
    if isinstance(raw, str):
        return normalize(raw)
    return DEFAULT_LOCALE


def save(root: Path, locale: str) -> str:
    resolved = normalize(locale)
    path = settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"locale": resolved}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return resolved
