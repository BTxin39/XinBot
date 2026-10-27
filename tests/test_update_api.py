"""更新检查接口的契约测试。

清单路径通过 `manifest_path()` 注入，测试不碰真实 `data/`。
"""

import json

import pytest

from app.interfaces.web.routes import update as update_route
from tests.test_web_cards import client as web_client  # noqa: F401  (pytest fixture)


@pytest.fixture
def manifest(tmp_path, monkeypatch):
    path = tmp_path / "update.json"
    monkeypatch.setattr(update_route, "manifest_path", lambda: path)
    return path


def write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_no_manifest_reports_present_false(web_client, manifest):
    payload = web_client.get("/api/update").json()["data"]
    assert payload["manifest_present"] is False
    assert payload["update"] is None
    assert payload["current"]


def test_manifest_without_update(web_client, manifest):
    write(manifest, {"version": "0.0.1"})
    payload = web_client.get("/api/update").json()["data"]
    assert payload["manifest_valid"] is True
    assert payload["update"] is None


def test_manifest_with_newer_version(web_client, manifest):
    write(manifest, {
        "version": "99.0.0",
        "url": "https://example.com/new.zip",
        "notes": "测试",
    })
    payload = web_client.get("/api/update").json()["data"]
    assert payload["update"]["latest"] == "99.0.0"
    assert payload["update"]["url"].endswith("new.zip")


def test_broken_manifest_is_reported_not_500(web_client, manifest):
    manifest.write_text("{broken", encoding="utf-8")
    response = web_client.get("/api/update")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["manifest_present"] is True
    assert payload["manifest_valid"] is False
    assert payload["update"] is None


def test_manifest_with_invalid_version(web_client, manifest):
    write(manifest, {"version": "abc"})
    payload = web_client.get("/api/update").json()["data"]
    assert payload["manifest_valid"] is False
