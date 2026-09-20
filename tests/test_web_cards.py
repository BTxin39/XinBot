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
from app.web.agent_manager import AgentManager
from app.web.character_cards import read_card, validate_card, export_card
from app.web.routes import models
from app.web.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app.core.persona as persona_module
    import app.config.runtime as runtime_module
    monkeypatch.setattr(persona_module, "PERSONAS_PATH", tmp_path / "personas.json")
    monkeypatch.setattr(runtime_module, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(PersonaStore, "_instance", None)
    monkeypatch.setattr(AgentManager, "_instance", None)
    monkeypatch.setattr(models, "ROOT", tmp_path)
    monkeypatch.setattr(models, "UPLOAD_ROOT", tmp_path / "pets")
    monkeypatch.setattr(models, "LLMRegistry", lambda: LLMRegistry(tmp_path / "registry.json"))
    PersonaStore.get().add_persona(Persona(name="xin", display_name="Xin", builtin=True))
    RuntimeConfig().save()
    with TestClient(app, raise_server_exceptions=False) as instance:
        yield instance


def card():
    return {"spec": "chara_card_v2", "spec_version": "2.0", "custom": "preserved", "data": {
        "name": "Haru", "description": "{{char}} greets {{user}}", "scenario": "Garden",
        "first_mes": "Hello", "extensions": {"custom": [1, 2]},
        "character_book": {"entries": []}, "post_history_instructions": "Be concise"}}


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
    import app.web.agent_manager as manager_module
    messages = []
    fake = SimpleNamespace(
        persona=Persona(name="haru", display_name="Haru", character_card=validate_card(card())),
        tool_manager=SimpleNamespace(),
        memory=SimpleNamespace(get_message=lambda: messages, add_message=lambda **message: messages.append(message)))
    monkeypatch.setattr(AgentManager, "_instance", None)
    monkeypatch.setattr(manager_module, "Agent", lambda config: fake)
    AgentManager.get()
    AgentManager.get()
    assert messages == [{"role": "assistant", "content": "Hello"}]


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
    monkeypatch.setenv("XINBOT_TEST_API_KEY", "")
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
    monkeypatch.setattr(AgentManager, "chat", lambda message: "Reply: " + message)
    assert client.post("/api/chat", json={"message": "hello"}).json()["data"]["reply"] == "Reply: hello"
    with client.websocket_connect("/ws/chat") as socket:
        socket.send_json({"message": "hello"})
        assert socket.receive_json() == {"chunk": "Reply: hello"}
        assert socket.receive_json() == {"done": True}
        socket.send_text("bad")
        assert "error" in socket.receive_json()


def test_chunking_terminates():
    assert len(DocumentChunker(10, 3).chunk("a" * 20)) == 3
    with pytest.raises(ValueError):
        DocumentChunker(10, 10)
