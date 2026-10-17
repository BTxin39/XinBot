"""外观模型的删除/重命名、日志导出的契约测试。

对应 docs/DECISIONS_v0.2.1.md §3 计划外补强 1（重复导入）与后续建议 1、3。
"""

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app import logs as log_store
from app.interfaces.cli.app import app
from app.interfaces.web.routes import models as models_route
from app.services import live2d_service as L
from tests.test_live2d_import import (
    cubism2_files,
    cubism2_named,
    cubism3_files,
    cubism3_named,
    make_zip,
)
from tests.test_web_cards import client as web_client  # noqa: F401  (fixture)


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """把导入目录与运行时目录都隔离到 tmp_path。"""
    upload = tmp_path / "imported"
    monkeypatch.setattr(L, "UPLOAD_ROOT", upload)
    monkeypatch.setattr(models_route, "live2d_service", L)
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "live2dcubismcore.min.js").write_text("x")
    (vendor / "live2d.min.js").write_text("x")
    monkeypatch.setattr(L, "vendor_root", lambda: vendor)
    return upload


def _import(tmp_path: Path, name: str, files: dict) -> dict:
    archive_path = tmp_path / name
    archive_path.write_bytes(make_zip(files))
    return L.import_from_path(archive_path)


# ── remove ────────────────────────────────────────────────────────


def test_remove_model(tmp_path, upload_dir):
    _import(tmp_path, "a.zip", cubism3_files())
    assert [row["name"] for row in L.catalog()] == ["model"]

    result = L.remove_model("model")
    assert result["name"] == "model"
    assert result["container_removed"] is True
    assert L.catalog() == []
    # 容器目录应被清掉，不留下空壳
    assert list(upload_dir.iterdir()) == []


def test_remove_unknown_model_reports_available(tmp_path, upload_dir):
    _import(tmp_path, "a.zip", cubism3_files())
    with pytest.raises(L.ModelImportError) as excinfo:
        L.remove_model("nope")
    assert excinfo.value.code == "missing"
    assert "model" in excinfo.value.detail


def test_remove_keeps_other_models_in_same_container(tmp_path, upload_dir):
    """手工把两个模型塞进同一容器时，只删目标，不误删另一个。"""
    _import(tmp_path, "a.zip", cubism3_named("alpha"))
    _import(tmp_path, "b.zip", cubism2_named("beta"))
    container = upload_dir / "shared"
    container.mkdir()
    # 把两个模型搬到同一个容器里，模拟历史手工整理的结果
    for row in L.catalog():
        target = container / row["manifest"].parent.name
        row["manifest"].parent.rename(target)
    for stray in list(upload_dir.iterdir()):
        if stray != container:
            stray.rmdir()

    L.remove_model("alpha")
    remaining = [row["name"] for row in L.catalog()]
    assert remaining == ["beta"]
    assert container.is_dir(), "共用容器不应被删除"


def test_remove_refuses_outside_upload_root(tmp_path, upload_dir):
    """安全边界：只允许删除导入目录之下的内容。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.model3.json").write_text("{}")
    with pytest.raises(L.ModelImportError):
        L.remove_model("anything")
    # 目录仍然存在
    assert outside.is_dir()


def test_cli_model_remove(tmp_path, upload_dir, monkeypatch):
    _import(tmp_path, "a.zip", cubism3_files())
    result = CliRunner().invoke(app, ["model", "remove", "model", "--force"])
    assert result.exit_code == 0, result.output
    assert "已删除" in result.output
    assert L.catalog() == []


def test_cli_model_remove_missing(tmp_path, upload_dir):
    result = CliRunner().invoke(app, ["model", "remove", "ghost", "--force"])
    assert result.exit_code == 1
    assert "找不到模型" in result.output


# ── rename ────────────────────────────────────────────────────────


def test_rename_model_moves_dir_and_manifest(tmp_path, upload_dir):
    _import(tmp_path, "a.zip", cubism3_files())
    result = L.rename_model("model", "my-pet")
    assert result["old_name"] == "model"
    assert result["name"] == "my-pet"
    assert result["manifest"] == "my-pet.model3.json"
    # 目录与清单都要改名
    assert (upload_dir / result["location"].split("/")[-2] / "my-pet").is_dir()
    rows = L.catalog()
    assert [row["name"] for row in rows] == ["my-pet"]
    # 改名后仍然能通过校验（引用都是相对路径）
    L.validate(L.ModelCandidate(manifest=rows[0]["manifest"], root=rows[0]["manifest"].parent,
                                kind="cubism3", name="my-pet"))


def test_rename_rejects_conflicting_name(tmp_path, upload_dir):
    _import(tmp_path, "a.zip", cubism3_named("alpha"))
    _import(tmp_path, "b.zip", cubism3_named("beta"))
    with pytest.raises(L.ModelImportError) as excinfo:
        L.rename_model("alpha", "beta")
    assert excinfo.value.code == "conflict"


@pytest.mark.parametrize("bad", ["", "   ", "a/b", "a\\b", "a:b", 'a<b'])
def test_rename_rejects_invalid_names(tmp_path, upload_dir, bad):
    _import(tmp_path, "a.zip", cubism3_files())
    with pytest.raises(L.ModelImportError) as excinfo:
        L.rename_model("model", bad)
    assert excinfo.value.code == "invalid_name"


def test_rename_same_name_is_rejected(tmp_path, upload_dir):
    _import(tmp_path, "a.zip", cubism3_files())
    with pytest.raises(L.ModelImportError):
        L.rename_model("model", "model")


def test_cli_model_rename(tmp_path, upload_dir):
    _import(tmp_path, "a.zip", cubism3_files())
    result = CliRunner().invoke(app, ["model", "rename", "model", "renamed"])
    assert result.exit_code == 0, result.output
    assert "已重命名" in result.output
    assert [row["name"] for row in L.catalog()] == ["renamed"]


# ── Web 接口 ──────────────────────────────────────────────────────


def test_web_delete_and_rename_endpoints(web_client, tmp_path):
    upload = L.UPLOAD_ROOT
    upload.mkdir(parents=True, exist_ok=True)
    import_result = L.import_from_bytes(make_zip(cubism3_files()))
    assert import_result["name"] == "model"

    renamed = web_client.put("/api/pet/models/model", json={"name": "web-renamed"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["model"]["name"] == "web-renamed"

    deleted = web_client.delete("/api/pet/models/web-renamed")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["removed"]["name"] == "web-renamed"


def test_web_delete_unknown_returns_404(web_client):
    assert web_client.delete("/api/pet/models/ghost").status_code == 404


def test_web_rename_duplicate_returns_409(web_client):
    L.UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    L.import_from_bytes(make_zip(cubism3_named("one")))
    L.import_from_bytes(make_zip(cubism3_named("two")))
    response = web_client.put("/api/pet/models/one", json={"name": "two"})
    assert response.status_code == 409


# ── 日志导出 ──────────────────────────────────────────────────────


def test_log_export_is_plain_text_with_header(web_client):
    import logging
    log_store.install()
    logging.getLogger("app.test").warning("导出行")
    response = web_client.get("/api/logs/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "attachment" in response.headers["content-disposition"]
    body = response.text
    assert body.startswith("# XinBot 运行日志导出")
    assert "导出行" in body
    assert "WARNING" in body
    # 导出应带完整日期，而不是只有时分秒
    assert body.count("-") >= 2


def test_log_export_respects_level_filter(web_client):
    import logging
    log_store.install()
    logging.getLogger("app.test").info("info-only")
    logging.getLogger("app.test").error("error-only")
    body = web_client.get("/api/logs/export", params={"level": "ERROR"}).text
    assert "error-only" in body
    assert "info-only" not in body


def test_cli_logs_export_writes_file(tmp_path, monkeypatch):
    """CLI 导出走真实后端 HTTP；这里用 TestClient 充当后端，验证写文件逻辑。"""
    import app.interfaces.cli.logs as logs_cli

    # 让 CLI 的 httpx 请求打到 TestClient 背后的 ASGI 应用
    from fastapi.testclient import TestClient
    from app.interfaces.web.server import app as web_app

    transport = TestClient(web_app, base_url="http://127.0.0.1:3796")

    class Proxy:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def get(self, url, params=None):
            path = "/" + url.split("/", 3)[3] if url.count("/") >= 3 else "/"
            return transport.get(path, params=params)

    monkeypatch.setattr(logs_cli.httpx, "Client", Proxy)
    import logging
    log_store.install()
    logging.getLogger("app.test").warning("导出验证")

    target = tmp_path / "out" / "logs.log"
    result = CliRunner().invoke(app, ["logs", "export", "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert target.is_file()
    content = target.read_text(encoding="utf-8")
    assert content.startswith("# XinBot 运行日志导出")
    assert "导出验证" in content
