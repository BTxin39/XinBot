"""Chat 模块已重构。

旧的 chat 对话逻辑已迁移至:
- xinbot start cli  → 完整桌面宠物 UI
- xinbot debug      → 纯文本调试对话

此文件保留以维持包导入兼容性。
"""

import typer

chat_app = typer.Typer()
