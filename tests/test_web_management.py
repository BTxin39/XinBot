from io import BytesIO
import json

import httpx
from PIL import Image
import pytest

from tests.test_web_cards import client
from app.config.runtime import RuntimeConfig
from app.web.credentials import credential_name
from app.web.routes import models
from app.storage.sqlite_store import SQLiteStore


def connection(**changes):
    return {"name": "secure-test", "base_url": "https://example.com/v1",
            "model": "test-model", "api_key": "sk-test-only", **changes}


@pytest.mark.parametrize("secret", ["key\nEVIL=1", "${HOME}", "key'quote", 'key"quote', "key\\escape"])
def test_env_injection_rejected(client, tmp_path, secret):
    response = client.post("/api/models", json=connection(api_key=secret))
    assert response.status_code == 422
    assert not (tmp_path / ".env").exists()
    assert secret not in response.text


def test_keys_and_models(client, tmp_path, monkeypatch):
    name = credential_name("secure-test")
    monkeypatch.delenv(name, raising=False)
    assert name != credential_name("secure_test")
    response = client.post("/api/models", json=connection())
    assert response.status_code == 200
    assert "sk-test-only" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/api/models", json=connection(api_key="", base_url="https://other.example/v1")).status_code == 409
    assert client.put("/api/providers/secure-test/key", json={"api_key": "sk-rotated"}).status_code == 200
    assert "sk-rotated" in (tmp_path / ".env").read_text()
    assert client.post("/api/models/register", json={"name": "extra/model", "provider": "secure-test"}).status_code == 200
    assert client.delete("/api/models/extra/model").status_code == 200
    assert client.delete("/api/providers/secure-test").status_code == 409
    assert client.delete("/api/providers/secure-test/key").status_code == 200
    assert "sk-rotated" not in (tmp_path / ".env").read_text()
    assert client.delete("/api/models/test-model").status_code == 200
    assert client.delete("/api/providers/secure-test").status_code == 200


@pytest.mark.parametrize("url", ["http://remote.example/v1", "https://user:pass@example.com/v1", "https://example.com/v1?key=value"])
def test_unsafe_endpoints(client, url):
    assert client.post("/api/models", json=connection(base_url=url)).status_code == 422


def test_ollama_discovery(client, monkeypatch):
    original = httpx.Client
    def handle(request):
        assert str(request.url) == "http://127.0.0.1:11434/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen3:8b", "size": 123}]})
    monkeypatch.setattr(models.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    response = client.post("/api/ollama/models", json={})
    assert response.json()["data"][0]["name"] == "qwen3:8b"
    assert client.post("/api/ollama/models", json={"base_url": "https://remote.example"}).status_code == 422
    response = client.post("/api/models", json=connection(name="local", base_url="http://127.0.0.1:11434", api_key="", provider_type="ollama"))
    assert response.status_code == 200
    provider = next(item for item in response.json()["data"]["providers"] if item["name"] == "local")
    assert provider["base_url"].endswith("/v1")
    assert not provider["has_key"]


def test_memory_workflow(client):
    assert client.post("/api/memory", json={"name": "../escape"}).status_code == 422
    assert client.post("/api/memory", json={"name": "scratch"}).status_code == 200
    assert client.post("/api/memory", json={"name": "scratch"}).status_code == 409
    response = client.put("/api/memory/scratch", json={"description": "test", "messages": [{"role": "user", "content": "hello"}], "profile": {"user_name": "Tester"}})
    assert response.json()["data"]["profile"]["user_name"] == "Tester"
    assert client.post("/api/memory/terminal", json={"command": "powershell whoami"}).status_code == 422
    response = client.post("/api/memory/terminal", json={"command": "clear scratch"})
    assert response.json()["data"]["confirmation_required"]
    assert len(client.get("/api/memory/scratch").json()["data"]["messages"]) == 1
    assert client.post("/api/memory/terminal", json={"command": "clear scratch", "confirm": True}).status_code == 200
    assert client.get("/api/memory/scratch").json()["data"]["messages"] == []
    assert client.post("/api/memory/scratch/activate").status_code == 200
    assert client.delete("/api/memory/scratch").status_code == 409
    assert client.post("/api/memory", json={"name": "other"}).status_code == 200
    assert client.post("/api/memory/other/activate").status_code == 200
    assert client.delete("/api/memory/scratch").status_code == 200
    assert client.get("/api/memory/scratch").status_code == 404


def test_ascii_and_port(client):
    buffer = BytesIO()
    Image.new("RGB", (32, 32), "black").save(buffer, "PNG")
    for mode in ("ascii", "braille"):
        response = client.post("/api/ascii", files={"file": ("test.png", buffer.getvalue(), "image/png")}, data={"width": 20, "mode": mode})
        assert response.status_code == 200
        assert response.json()["data"]["text"]
    assert client.post("/api/ascii", files={"file": ("bad.png", b"invalid")}).status_code == 422
    assert client.post("/api/config", json={"web_port": 70000}).status_code == 422
    assert client.post("/api/config", json={"web_port": 8123}).status_code == 200
    assert RuntimeConfig.load().web_port == 8123


def test_latest_memory(tmp_path):
    store = SQLiteStore(str(tmp_path / "messages.db"))
    try:
        for number in range(5):
            store.insert_message("test", {"role": "user", "content": str(number)})
        assert [item["content"] for item in store.get_messages("test", 2)] == ["3", "4"]
    finally:
        store.engine.dispose()


def test_cross_site_write_blocked(client):
    assert client.post("/api/memory", json={"name": "blocked"}, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/config", headers={"host": "evil.example"}).status_code == 400
    assert client.post("/api/config", json={"mcp_servers": []}).status_code == 422


def test_ollama_failure(client, monkeypatch):
    original = httpx.Client
    def handle(request):
        raise httpx.ConnectError("not installed", request=request)
    monkeypatch.setattr(models.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    response = client.post("/api/ollama/models", json={})
    assert response.status_code == 502
    assert response.json()["ok"] is False


def test_ollama_chat_contract(monkeypatch):
    from openai import OpenAI
    from app.llm.registry import ProviderConfig
    from app.llm.providers.factory import create_provider_from_config
    import app.llm.providers.openai_provider as provider_module
    def handle(request):
        assert str(request.url) == "http://127.0.0.1:11434/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer ollama"
        assert json.loads(request.content)["model"] == "qwen3:8b"
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 1, "model": "qwen3:8b", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "hello"}}]})
    monkeypatch.setattr(provider_module, "OpenAI", lambda **kwargs: OpenAI(http_client=httpx.Client(transport=httpx.MockTransport(handle)), **kwargs))
    provider = create_provider_from_config(ProviderConfig(name="local", provider_type="ollama", api_key_env="UNSET_TEST_OLLAMA_API_KEY", base_url="http://127.0.0.1:11434/v1"))
    try:
        assert provider.chat([{"role": "user", "content": "hi"}], "qwen3:8b", 0.7).content == "hello"
    finally:
        provider.client.close()


def test_deleted_memory_does_not_remigrate(tmp_path):
    (tmp_path / "legacy_memory.json").write_text(json.dumps([{"role": "user", "content": "legacy"}]))
    store = SQLiteStore(str(tmp_path / "messages.db"))
    try:
        store.migrate_from_json(str(tmp_path))
        assert store.get_message_count("legacy") == 1
        store.delete_memory("legacy")
        store.migrate_from_json(str(tmp_path))
        assert store.get_message_count("legacy") == 0
    finally:
        store.engine.dispose()


def test_env_name_guard(tmp_path):
    from app.web.credentials import write_secret
    with pytest.raises(ValueError):
        write_secret(tmp_path, "PYTHONPATH", "malicious")
    assert not (tmp_path / ".env").exists()
