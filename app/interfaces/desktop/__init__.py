"""桌面常驻桌宠的适配器层（Windows 窗口壳）。

设计要点见 docs/DECISIONS/DECISIONS_v0.2.2.md：
  - 只用 pywebview + pywin32，不引入 Electron/Tauri；
  - 透明靠 `transparent=True` + 窗体 `BackColor == TransparencyKey`（P0 实测）；
  - 本进程**不创建 Agent**，对话全部走后端。

模块划分：
  geometry.py  纯几何（可单测，不碰 Windows API）
  settings.py  data/desktop_pet.json 读写
  win32_api.py 窗口样式/显示器/鼠标状态
  shell.py     轮询循环与右键菜单
"""

from app.interfaces.desktop.geometry import (
    Monitor,
    Rect,
    clamp_scale,
    clamp_to_monitors,
    hit_test,
    scale_for_monitor,
)
from app.interfaces.desktop.settings import PetWindowState, load, save, state_path

__all__ = [
    "Monitor",
    "Rect",
    "clamp_scale",
    "clamp_to_monitors",
    "hit_test",
    "scale_for_monitor",
    "PetWindowState",
    "load",
    "save",
    "state_path",
]
