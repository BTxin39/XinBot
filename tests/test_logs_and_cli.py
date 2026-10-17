"""运行日志可视化与 CLI 命令的测试。

覆盖：
    - `app/logs.py` 的环形缓冲（容量、级别过滤、状态摘要）
    - `/api/logs` 接口（CLI 与 Web 共用的唯一日志来源）
    - `xinbot model import` / `model list` / `model runtimes` 的行为
"""

import logging

import pytest
from typer.testing import CliRunner

from app import logs as log_store
from app.interfaces.cli.app import app
from app.services import live2d_service as L
from tests.test_live2d_import import cubism2_files, cubism3_files, make_zip
from tests.test_web_cards import client as web_client  # noqa: F401  (pytest fixture)


# ── 日志缓冲 ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_logs():
    log_store.install()
    log_store.reset()
    yield
    log_store.reset()


def test_install_is_idempotent():
    log_store.install()
    log_store.install()
    logging.getLogger("xinbot").info("hello")
    entries = log_store.entries()
    assert sum(1 for item in entries if item["message"] == "hello") == 1


def test_entries_capture_message_and_level():
    logging.getLogger("app.test").warning("注意一下")
    entries = log_store.entries()
    assert entries[-1]["message"] == "注意一下"
    assert entries[-1]["level"] == "WARNING"
    assert entries[-1]["stamp"]


def test_level_filter():
    logger = logging.getLogger("app.test")
    logger.info("普通")
    logger.error("出错")
    only_errors = log_store.entries(min_level="ERROR")
    messages = [item["message"] for item in only_errors]
    assert "出错" in messages
    assert "普通" not in messages


def test_limit_returns_tail():
    logger = logging.getLogger("app.test")
    for index in range(10):
        logger.info("第 %d 条", index)
    entries = log_store.entries(limit=3)
    messages = [item["message"] for item in entries]
    assert messages[-1] == "第 9 条"
    assert messages[-2] == "第 8 条"
    assert len(messages) == 3


def test_ring_buffer_respects_capacity():
    logger = logging.getLogger("app.test")
    for index in range(log_store.DEFAULT_CAPACITY + 25):
        logger.info("n%d", index)
    entries = log_store.entries(limit=log_store.DEFAULT_CAPACITY + 100)
    assert len(entries) == log_store.DEFAULT_CAPACITY
    # 最旧的被挤掉，最新的保留
    assert entries[-1]["message"] == f"n{log_store.DEFAULT_CAPACITY + 24}"


def test_status_counts_warnings_and_errors():
    logger = logging.getLogger("app.test")
    logger.warning("w1")
    logger.error("e1")
    status = log_store.status()
    assert status["warnings"] >= 1
    assert status["errors"] >= 1
    assert status["buffered"] >= 2
    assert status["capacity"] == log_store.DEFAULT_CAPACITY


def test_reset_clears_buffer():
    logging.getLogger("app.test").info("x")
    log_store.reset()
    assert log_store.entries() == []


def test_exception_traceback_is_captured():
    """异常日志必须带堆栈。

    v0.2.1 排查一个 500 时，UI 里只显示 "Exception in ASGI application"，
    没有任何堆栈信息，等于没法定位。这条测试锁住"堆栈必须进缓冲"。
    """
    logger = logging.getLogger("app.test")
    try:
        raise ValueError("模拟异常")
    except ValueError:
        logger.exception("处理请求失败")

    entry = log_store.entries()[-1]
    assert entry["level"] == "ERROR"
    assert "处理请求失败" in entry["message"]
    assert "Traceback" in entry["message"]
    assert "ValueError" in entry["message"]


def test_exception_export_keeps_traceback(web_client):
    """导出文件里也必须能看到堆栈，否则归档后同样查不动。"""
    logger = logging.getLogger("app.test")
    try:
        raise RuntimeError("导出用异常")
    except RuntimeError:
        logger.exception("失败")
    body = web_client.get("/api/logs/export").text
    assert "RuntimeError" in body


# ── /api/logs 接口 ────────────────────────────────────────────────


def test_api_returns_entries_and_status(web_client):
    logging.getLogger("app.test").info("来自后端")
    response = web_client.get("/api/logs", params={"limit": 20})
    assert response.status_code == 200
    data = response.json()["data"]
    assert "status" in data and "entries" in data
    assert any(item["message"] == "来自后端" for item in data["entries"])


def test_api_rejects_out_of_range_limit(web_client):
    assert web_client.get("/api/logs", params={"limit": 0}).status_code == 422
    assert web_client.get("/api/logs", params={"limit": 999}).status_code == 422


def test_api_status_endpoint(web_client):
    payload = web_client.get("/api/logs/status").json()["data"]
    assert payload["capacity"] == log_store.DEFAULT_CAPACITY
    assert "uptime_seconds" in payload


def test_api_clear(web_client):
    logging.getLogger("app.test").info("待清空")
    assert web_client.delete("/api/logs").json()["data"]["cleared"] is True
    # 清空请求自身的访问日志会在清空之后写入，因此这里只断言旧记录已消失
    messages = [item["message"] for item in log_store.entries()]
    assert "待清空" not in messages


def test_api_level_filter(web_client):
    logger = logging.getLogger("app.test")
    logger.info("info-line")
    logger.error("error-line")
    payload = web_client.get("/api/logs", params={"level": "ERROR"}).json()["data"]
    messages = [item["message"] for item in payload["entries"]]
    assert "error-line" in messages
    assert "info-line" not in messages


# ── CLI：model 命令 ───────────────────────────────────────────────


def _write_zip(tmp_path, name, files):
    target = tmp_path / name
    target.write_bytes(make_zip(files))
    return target


def test_cli_model_import_cubism3(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "UPLOAD_ROOT", tmp_path / "imported")
    monkeypatch.setattr(L, "vendor_root", lambda: tmp_path / "vendor")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "live2dcubismcore.min.js").write_text("x")

    source = _write_zip(tmp_path, "m.zip", cubism3_files())
    result = CliRunner().invoke(app, ["model", "import", str(source)])
    assert result.exit_code == 0, result.output
    assert "已导入" in result.output
    assert "cubism3" in result.output


def test_cli_model_import_reports_missing_runtime(tmp_path, monkeypatch):
    """缺 Cubism 2.1 运行时：要给出可操作提示，而不是笼统失败。"""
    monkeypatch.setattr(L, "UPLOAD_ROOT", tmp_path / "imported")
    monkeypatch.setattr(L, "vendor_root", lambda: tmp_path / "vendor")
    (tmp_path / "vendor").mkdir()

    source = _write_zip(tmp_path, "old.zip", cubism2_files())
    result = CliRunner().invoke(app, ["model", "import", str(source)])
    assert result.exit_code == 1
    assert "live2d.min.js" in result.output


def test_cli_model_import_missing_file(tmp_path):
    result = CliRunner().invoke(app, ["model", "import", str(tmp_path / "nope.zip")])
    assert result.exit_code == 1
    assert "找不到文件" in result.output


def test_cli_model_import_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    result = CliRunner().invoke(app, ["model", "import", str(bad)])
    assert result.exit_code == 1
    assert "导入失败" in result.output


def test_cli_model_list_and_runtimes(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "UPLOAD_ROOT", tmp_path / "imported")
    monkeypatch.setattr(L, "vendor_root", lambda: tmp_path / "vendor")
    (tmp_path / "vendor").mkdir()

    runner = CliRunner()
    empty = runner.invoke(app, ["model", "list"])
    assert empty.exit_code == 0
    assert "还没有导入" in empty.output

    runtimes = runner.invoke(app, ["model", "runtimes"])
    assert runtimes.exit_code == 0
    assert "cubism2" in runtimes.output.lower() or "Cubism" in runtimes.output


# ── CLI：logs 命令 ────────────────────────────────────────────────


def test_cli_logs_without_backend_explains_what_to_do(monkeypatch):
    """后端未运行时应明确提示，而不是打印空列表。

    必须把端口指向一个必然空闲的端口：否则本机若正好开着后端，
    这条测试会因为"真的读到了日志"而失败——那是环境依赖，不是被测行为。
    """
    import app.interfaces.cli.logs as logs_cli

    monkeypatch.setattr(logs_cli, "_base_url", lambda: "http://127.0.0.1:1")
    result = CliRunner().invoke(app, ["logs"])
    assert result.exit_code == 1
    assert "后端可能未运行" in result.output


def test_cli_help_lists_new_commands():
    output = CliRunner().invoke(app, ["--help"]).output
    for command in ("model", "logs", "start", "rag"):
        assert command in output
