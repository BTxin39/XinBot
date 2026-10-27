"""主题（皮肤）预设。

背景：原样式表里颜色是**全硬编码**的（73 种色值、没有 CSS 变量），
直接做"深色模式"要重写全部 16 个视图的样式，风险极高。
所以这里采取**变量 + 定向覆盖**：
    * 只把"主要表面色"抽成变量（背景、卡片、边框、文字、强调色）；
    * `theme.css` 用这些变量覆盖关键选择器；
    * 默认主题的变量值 = 改造前完全一样的色值 → **零视觉回归**（有像素级验证）。

这样换主题只改一层变量，不用碰组件。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

DEFAULT_THEME = "spring"


@dataclass(frozen=True)
class Theme:
    """一套配色。字段名对应 `theme.css` 里的 CSS 变量。"""

    name: str
    label: str
    description: str
    variables: dict[str, str] = field(default_factory=dict)


# 变量语义（与 theme.css 一一对应）
#   --xin-bg          应用底色
#   --xin-surface     卡片 / 顶栏 / 侧栏底色
#   --xin-surface-2   次级表面（角色区、预览底）
#   --xin-border      分隔线
#   --xin-text        正文
#   --xin-text-muted  次要文字
#   --xin-accent      主色（品牌、主按钮、链接）
#   --xin-accent-strong 主色悬停
#   --xin-accent-soft   主色淡底（选中态）

THEMES: dict[str, Theme] = {
    "spring": Theme(
        name="spring",
        label="春绿",
        description="默认配色：浅底绿调",
        variables={
            "--xin-bg": "#f8faf9",
            "--xin-surface": "#ffffff",
            # 取 workspace.css 里 .companion 的最终值（style.css 是 #eff3ee，
            # 但被 workspace.css 覆盖成 #edf4ef）——用最终值才能零视觉回归。
            "--xin-surface-2": "#edf4ef",
            "--xin-border": "#dce3df",
            "--xin-text": "#273730",
            "--xin-text-muted": "#78867e",
            "--xin-accent": "#376f55",
            "--xin-accent-strong": "#2a5c44",
            "--xin-accent-soft": "#eaf2ed",
        },
    ),
    "amber": Theme(
        name="amber",
        label="暖阳",
        description="暖米底 + 琥珀色强调",
        variables={
            "--xin-bg": "#fbf7f0",
            "--xin-surface": "#fffdf9",
            "--xin-surface-2": "#f5ecdf",
            "--xin-border": "#e6dac8",
            "--xin-text": "#3a3128",
            "--xin-text-muted": "#8a7a67",
            "--xin-accent": "#a2652a",
            "--xin-accent-strong": "#85511f",
            "--xin-accent-soft": "#f6e8d6",
        },
    ),
    "ocean": Theme(
        name="ocean",
        label="海蓝",
        description="冷蓝底 + 藏青强调",
        variables={
            "--xin-bg": "#f5f8fb",
            "--xin-surface": "#ffffff",
            "--xin-surface-2": "#e9f0f7",
            "--xin-border": "#d6e0ea",
            "--xin-text": "#22303d",
            "--xin-text-muted": "#6f8296",
            "--xin-accent": "#2c5f86",
            "--xin-accent-strong": "#234d6d",
            "--xin-accent-soft": "#e4eef7",
        },
    ),
    "grape": Theme(
        name="grape",
        label="葡萄",
        description="淡紫底 + 梅色强调",
        variables={
            "--xin-bg": "#faf8fc",
            "--xin-surface": "#ffffff",
            "--xin-surface-2": "#f1ecf7",
            "--xin-border": "#e2d9ee",
            "--xin-text": "#2f2838",
            "--xin-text-muted": "#7d7189",
            "--xin-accent": "#6b4a8d",
            "--xin-accent-strong": "#573a75",
            "--xin-accent-soft": "#f0e8f8",
        },
    ),
}


def list_themes() -> list[dict]:
    """返回给前端的主题列表（含变量，前端直接 setProperty）。"""
    return [
        {
            "name": theme.name,
            "label": theme.label,
            "description": theme.description,
            "variables": dict(theme.variables),
        }
        for theme in THEMES.values()
    ]


def resolve(name: str | None) -> Theme:
    """按名字取主题；未知名字回落默认（不要让主题错了就白屏）。"""
    return THEMES.get((name or "").strip().lower()) or THEMES[DEFAULT_THEME]


def validate(name: str) -> str | None:
    if (name or "").strip().lower() not in THEMES:
        available = "、".join(theme.name for theme in THEMES.values())
        return f"没有这个主题：{name}（可选：{available}）"
    return None


# ── 持久化 ────────────────────────────────────────────────────────

def settings_path(root):
    from pathlib import Path

    return Path(root) / "data" / "theme.json"


def load(root) -> str:
    import pathlib

    path = settings_path(root)
    if not pathlib.Path(path).is_file():
        return DEFAULT_THEME
    try:
        raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_THEME
    if isinstance(raw, dict):
        return resolve(str(raw.get("name", ""))).name
    return DEFAULT_THEME


def save(root, name: str) -> str:
    import pathlib

    resolved = resolve(name).name
    path = pathlib.Path(settings_path(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"name": resolved}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return resolved
