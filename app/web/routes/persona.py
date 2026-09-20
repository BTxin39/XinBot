from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config.runtime import RuntimeConfig
from app.core.persona import Persona, PersonaStore
from app.web.agent_manager import AgentManager
from app.web.character_cards import export_card, read_card, validate_card

router = APIRouter(prefix="/api/persona")
AVATARS = Path("data/web_uploads/avatars")


class PersonaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="", max_length=100, pattern=r"^[\w-]*$")
    display_name: str = Field(min_length=1, max_length=200)
    traits: list[str] = Field(default_factory=list)
    speaking_style: str = ""
    background: str = ""
    constraints: list[str] = Field(default_factory=list)
    character_card: dict = Field(default_factory=dict)
    pet_model: str = ""


def find(name):
    persona = PersonaStore.get().get_persona(name)
    if not persona:
        raise HTTPException(404, "角色不存在")
    return persona


@router.get("")
def list_personas():
    return {"ok": True, "data": [persona.to_dict() for persona in PersonaStore.get().list_personas()]}


@router.post("")
def create_persona(body: PersonaInput):
    with AgentManager.lock:
        values = body.model_dump()
        values["name"] = values["name"] or f"character-{uuid4().hex[:12]}"
        if values["character_card"]:
            values["character_card"] = validate_card(values["character_card"])
        persona = Persona(**values)
        PersonaStore.get().add_persona(persona)
        return {"ok": True, "data": persona.to_dict()}


@router.post("/import")
def import_persona(file: UploadFile):
    card, avatar = read_card(file.file.read(20 * 1024 * 1024 + 1), file.filename or "card.json")
    name = f"character-{uuid4().hex[:12]}"
    persona = Persona(name=name, display_name=card["data"]["name"], character_card=card)
    if avatar:
        AVATARS.mkdir(parents=True, exist_ok=True)
        (AVATARS / f"{name}.png").write_bytes(avatar)
        persona.avatar = f"/media/avatars/{name}.png"
    with AgentManager.lock:
        PersonaStore.get().add_persona(persona)
    return {"ok": True, "data": persona.to_dict()}


@router.get("/{name}/export")
def export_persona(name: str):
    return JSONResponse(export_card(find(name)), headers={"Content-Disposition": 'attachment; filename="character.json"'})


@router.post("/{name}/activate")
def activate(name: str):
    with AgentManager.lock:
        persona = find(name)
        config = RuntimeConfig.load()
        config.persona_name = name
        config.current_memory_name = f"web-{name}"
        config.save()
        AgentManager.shutdown()
        return {"ok": True, "data": persona.to_dict()}


@router.put("/{name}")
def update_persona(name: str, body: PersonaInput):
    with AgentManager.lock:
        find(name)
        updates = body.model_dump(exclude={"name"})
        if updates["character_card"]:
            updates["character_card"] = validate_card(updates["character_card"])
            updates["character_card"]["data"]["name"] = body.display_name
        PersonaStore.get().update_persona(name, updates)
        if AgentManager._instance and AgentManager._instance.config.persona_name == name:
            AgentManager._instance.persona = find(name)
        return {"ok": True, "data": find(name).to_dict()}


@router.delete("/{name}")
def delete_persona(name: str):
    with AgentManager.lock:
        if RuntimeConfig.load().persona_name == name:
            raise HTTPException(409, "请先切换到其他角色")
        PersonaStore.get().remove_persona(name)
        return {"ok": True, "data": {"deleted": name}}
