import base64
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
import pytest

from app.config.runtime import RuntimeConfig
from app.core.persona import Persona, PersonaStore
from app.core.agent import Agent
from app.core.state import AgentState
from app.memory.profile import MemoryProfile
from app.llm.registry import LLMRegistry
from app.rag.document import DocumentChunker
from app.services.agent_runtime import AgentRuntime
from app.interfaces.web.character_cards import read_card, validate_card, export_card
from app.interfaces.web.routes import models
from app.interfaces.web.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app.core.persona as persona_module
    import app.config.runtime as runtime_module
    import app.llm.registry as registry_module

    monkeypatch.setattr(persona_module, "PERSONAS_PATH", tmp_path / "personas.json")
    monkeypatch.setattr(runtime_module, "CONFIG_PATH", tmp_path / "config.json")
    # 隔离 LLM 注册表：path 是 default 参数，构造时求值，因此要同时改默认值，
    # 否则 service 层（LLMConfigService）会用真实 data/llm_registry.json
    monkeypatch.setattr(registry_module, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(
        registry_module.LLMRegistry,
        "__init__",
        lambda self, path=tmp_path / "registry.json": _registry_init(self, path),
    )
    monkeypatch.setattr(PersonaStore, "_instance", None)
    AgentRuntime.reset_for_tests()
    monkeypatch.setattr(models, "ROOT", tmp_path)
    monkeypatch.setattr(models, "UPLOAD_ROOT", tmp_path / "pets")
    PersonaStore.get()
    RuntimeConfig(db_path=str(tmp_path / "memory.db")).save()
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as instance:
        yield instance


def _registry_init(self, path):
    """复刻 LLMRegistry.__init__，但强制使用隔离路径。"""
    self.path = path
    self.data = self._load()


def card():
    return {"spec": "chara_card_v2", "spec_version": "2.0", "custom": "preserved", "data": {
        "name": "Haru", "description": "{{char}} greets {{user}}", "scenario": "Garden",
        "first_mes": "Hello", "extensions": {"custom": [1, 2]},
        "character_book": {"entries": []}, "post_history_instructions": "Be concise"}}


def test_pet_storage_paths():
    from app.interfaces.web.server import ROOT
    from scripts.download_live2d import ROOT as download_root
    assert models.MODEL_ROOT == ROOT / "pet/live2d"
    assert models.UPLOAD_ROOT == ROOT / "pet/imported"
    assert download_root == ROOT / "pet"
    mounts = {route.path: Path(route.app.directory) for route in app.routes
              if hasattr(getattr(route, "app", None), "directory")}
    assert mounts["/models"] == models.MODEL_ROOT
    assert mounts["/media/pets"] == models.UPLOAD_ROOT
    assert mounts["/vendor"] == ROOT / "pet/vendor"
    assert mounts["/codexpet"] == ROOT / "pet/codexpet"


def test_card_roundtrip_and_prompt():
    result = validate_card(card())
    persona = Persona(name="haru", display_name="Haru", character_card=result)
    exported = export_card(persona)
    assert exported["custom"] == "preserved"
    assert exported["data"]["character_book"] == {"entries": []}
    assert exported["data"]["extensions"] == {"custom": [1, 2]}
    assert "Haru greets 用户" in persona.to_prompt_text()
    assert "Garden" in persona.to_prompt_text()


def test_post_history_instructions():
    agent = object.__new__(Agent)
    agent.persona = Persona(name="haru", display_name="Haru", character_card=validate_card(card()))
    agent.state = AgentState()
    agent.memory = SimpleNamespace(get_profile=MemoryProfile.empty, get_summary=lambda: "",
                                   get_message=lambda: [{"role": "user", "content": "hello"}])
    messages = agent._build_messages()
    assert messages[-1] == {"role": "system", "content": "Be concise"}
    assert messages[-2]["content"] == "hello"


def test_greeting_is_added_once(monkeypatch):
    import app.services.agent_runtime as runtime_module
    messages = []
    fake = SimpleNamespace(
        persona=Persona(name="haru", display_name="Haru", character_card=validate_card(card())),
        tool_manager=SimpleNamespace(),
        shutdown=lambda: None,
        memory=SimpleNamespace(get_message=lambda: messages, add_message=lambda **message: messages.append(message)))
    AgentRuntime.reset_for_tests()
    try:
        monkeypatch.setattr(runtime_module, "Agent", lambda config, approval_callback=None: fake)
        AgentRuntime.get()
        AgentRuntime.get()
        assert messages == [{"role": "assistant", "content": "Hello"}]
    finally:
        AgentRuntime.reset_for_tests()


def test_png_metadata():
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("chara", base64.b64encode(json.dumps(card()).encode()).decode())
    buffer = BytesIO()
    Image.new("RGBA", (16, 16)).save(buffer, format="PNG", pnginfo=metadata)
    result, avatar = read_card(buffer.getvalue(), "character.png")
    assert result["data"]["name"] == "Haru"
    assert Image.open(BytesIO(avatar)).size == (16, 16)


def test_persona_crud(client):
    response = client.post("/api/persona/import", files={"file": ("card.json", json.dumps(card()), "application/json")})
    assert response.status_code == 200
    name = response.json()["data"]["name"]
    assert client.get(f"/api/persona/{name}/export").json()["custom"] == "preserved"
    assert client.post(f"/api/persona/{name}/activate").json()["ok"]
    assert RuntimeConfig.load().current_memory_name == f"web-{name}"
    assert client.delete(f"/api/persona/{name}").status_code == 409
    client.post("/api/persona/xin/activate")
    assert client.delete(f"/api/persona/{name}").json()["ok"]
    assert client.delete("/api/persona/xin").status_code == 409


def test_invalid_inputs_and_origin(client):
    assert client.post("/api/persona/import", files={"file": ("bad.json", "[]")}).status_code == 422
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
    response = client.post("/api/config", json={"temperature": 9})
    assert response.status_code == 422 and response.json()["ok"] is False
    assert client.post("/api/persona", json={}, headers={"origin": "https://evil.example"}).status_code == 403


def test_keys_not_exposed(client, monkeypatch):
    from app.interfaces.web.credentials import credential_name
    monkeypatch.delenv(credential_name("test"), raising=False)
    connection = {"name": "test", "base_url": "https://example.com/v1", "model": "test-model", "api_key": "secret-value"}
    response = client.post("/api/models", json=connection)
    assert response.status_code == 200
    assert "secret-value" not in response.text
    connection["api_key"] = ""
    assert client.post("/api/models", json=connection).status_code == 200
    assert LLMRegistry(models.ROOT / "registry.json").get_provider("test").api_key == "secret-value"
    assert "secret-value" not in client.get("/api/config").text


def test_zip_traversal(client):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../outside.json", "{}")
    response = client.post("/api/pet/models/import", files={"file": ("bad.zip", buffer.getvalue())})
    assert response.status_code == 422


def test_sprite_zip(client):
    buffer = BytesIO()
    sprite = BytesIO()
    Image.new("RGBA", (80, 90)).save(sprite, format="WEBP")
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("pet.json", json.dumps({"displayName": "Sprite", "spritesheetPath": "spritesheet.webp"}))
        archive.writestr("spritesheet.webp", sprite.getvalue())
    response = client.post("/api/pet/models/import", files={"file": ("sprite.zip", buffer.getvalue())})
    assert response.status_code == 200
    assert any(item["name"] == "Sprite" for item in response.json()["data"])


def test_chat_transport(client, monkeypatch):
    monkeypatch.setattr(AgentRuntime, "chat", lambda user_input, **options: "Reply: " + user_input)
    assert client.post("/api/chat", json={"message": "hello"}).json()["data"]["reply"] == "Reply: hello"
    with client.websocket_connect("ws://127.0.0.1/ws/chat") as socket:
        socket.send_json({"message": "hello"})
        assert socket.receive_json() == {"chunk": "Reply: hello"}
        assert socket.receive_json() == {"done": True}
        socket.send_text("bad")
        assert "error" in socket.receive_json()


def test_chunking_terminates():
    assert len(DocumentChunker(10, 3).chunk("a" * 20)) == 3
    with pytest.raises(ValueError):
        DocumentChunker(10, 10)
