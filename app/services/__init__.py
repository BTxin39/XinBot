"""跨端业务编排层。

依赖方向（docs/DECISIONS/DECISIONS_V0.2.0.md §4、§8）：

    interfaces/{cli,web,commands}  →  services  →  core · config · memory · storage · rag · llm

约束（由 `tests/test_layering.py` 强制）：
    - 本层不得 import `fastapi`、`rich`、`typer`
    - 本层不得 import `app.interfaces` / `app.interfaces.cli` / `app.interfaces.web`
"""
