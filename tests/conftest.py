"""套件级护栏：测试不得改动真实的 data/ 目录。

背景（P3 执行中发现）：`tests/test_summarizer.py` 的 `ChatMemory` 用例没有隔离
`db_path`，于是每次跑测试都会对**用户的真实 `data/xinbot.db`** 执行
`clear()` 与写入（记忆名 `test_trim`）。这类缺陷很难靠代码评审发现，
因为单看测试文件完全合理。

因此这里在会话层面对整个 data/ 目录做前后指纹比对：
任何测试（含将来新增的）写坏用户数据都会**以失败退出码**报告，
而不是悄悄发生几个月后才被用户发现。

实现注意：基线快照存在 `tests/data_guard.py` 里，**不能**放本文件的模块级变量——
`conftest.py` 会被加载成两个不同的模块对象，放这里会让护栏静默失效（实测踩过）。

排查提示：若确认是本地人为生成 fixtures，可临时设置
`XINBOT_ALLOW_DATA_WRITES=1` 放宽；正常开发不应使用。
"""

import os

from tests import data_guard


def pytest_sessionstart(session):
    # 先做内容预检：捕获"更早的会话已经把真实 data/ 写坏"的情况，
    # 指纹比对只能发现本次会话期间的改动（P5 期间踩过，见 data_guard.precheck）。
    problems = data_guard.precheck()
    if problems and os.getenv("XINBOT_ALLOW_DATA_WRITES") != "1":
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        message = (
            "\n检测到 data/ 已被此前的测试运行污染：\n  "
            + "\n  ".join(problems)
            + "\n这会让应用静默指向临时数据库/注册表，请先把这些字段改回 data/ 下的真实路径。\n"
        )
        if reporter is not None:
            reporter.write_sep("=", "DATA PRE-EXISTING POLLUTION", red=True)
            reporter.write_line(message)
        else:  # pragma: no cover
            print(message)

    data_guard.capture_baseline()


def pytest_sessionfinish(session, exitstatus):
    if os.getenv("XINBOT_ALLOW_DATA_WRITES") == "1":
        return
    changes = data_guard.changes_since_baseline()
    if not any(changes.values()):
        return

    session.exitstatus = 1
    message = (
        "\n测试改动了真实的 data/ 目录（会破坏用户数据）：\n"
        + data_guard.describe(changes)
        + "\n请让相关用例用 tmp_path 隔离（例如 RuntimeConfig(db_path=...)），"
        "不要把这条护栏关掉。\n"
    )
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_sep("=", "DATA POLLUTION", red=True)
        reporter.write_line(message)
    else:  # pragma: no cover - 仅在无终端插件时走到
        print(message)
