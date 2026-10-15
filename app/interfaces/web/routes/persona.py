from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config.runtime import RuntimeConfig
from app.services.agent_runtime import AgentRuntime
from app.services.persona_service import PersonaService, PersonaServiceError
from app.interfaces.web.character_cards import export_card, read_card, validate_card
from app.interfaces.web.story import preview_story

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
    aliases: list[str] = Field(default_factory=list)
    history: str = ""
    knowledge_tags: list[str] = Field(default_factory=list)


def _http_error(error: PersonaServiceError) -> HTTPException:
    status = {"missing": 404, "active": 409}.get(error.code, 422)
    return HTTPException(status, str(error))


def find(name):
    """读取角色，不存在则 404（保持既有路由行为）。"""
    try:
        return PersonaService().get_persona(name)
    except PersonaServiceError as error:
        raise _http_error(error) from error


@router.get("")
def list_personas():
    return {"ok": True, "data": PersonaService().list_personas()}


@router.post("")
def create_persona(body: PersonaInput):
    with AgentRuntime.lock:
        values = body.model_dump()
        if values["character_card"]:
            values["character_card"] = validate_card(values["character_card"])
        try:
            persona = PersonaService().create_from_values(values)
        except PersonaServiceError as error:
            raise _http_error(error) from error
        return {"ok": True, "data": persona.to_dict()}


@router.post("/import")
def import_persona(file: UploadFile):
    card, avatar = read_card(file.file.read(20 * 1024 * 1024 + 1), file.filename or "card.json")
    with AgentRuntime.lock:
        try:
            persona = PersonaService().create_from_character_card(card)
        except PersonaServiceError as error:
            raise _http_error(error) from error
    if avatar:
        AVATARS.mkdir(parents=True, exist_ok=True)
        (AVATARS / f"{persona.name}.png").write_bytes(avatar)
        persona.avatar = f"/media/avatars/{persona.name}.png"
    return {"ok": True, "data": persona.to_dict()}


@router.post("/story/preview")
def story_preview(file: UploadFile, hints: str = Form("")):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".md", ".pdf"}:
        raise HTTPException(422, "仅支持 TXT、Markdown 或 PDF")
    content = file.file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "故事文件不能超过 2 MB")
    try:
        if suffix == ".pdf":
            from io import BytesIO
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages[:100])
        else:
            text = content.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(422, "无法解析故事文件") from exc
    return {"ok": True, "data": preview_story(text, hints)}


@router.get("/{name}/export")
def export_persona(name: str):
    return JSONResponse(export_card(find(name)), headers={"Content-Disposition": 'attachment; filename="character.json"'})


@router.post("/{name}/activate")
def activate(name: str):
    with AgentRuntime.lock:
        try:
            # D1 的唯一实现：切换角色同时切换角色专属记忆（CLI 走同一方法）
            persona = PersonaService().activate(name)
        except PersonaServiceError as error:
            raise _http_error(error) from error
        AgentRuntime.rebuild()
        return {"ok": True, "data": persona.to_dict()}


@router.put("/{name}")
def update_persona(name: str, body: PersonaInput):
    with AgentRuntime.lock:
        find(name)
        updates = body.model_dump(exclude={"name"})
        if updates["character_card"]:
            updates["character_card"] = validate_card(updates["character_card"])
            updates["character_card"]["data"]["name"] = body.display_name
        try:
            PersonaService().update(name, updates)
        except PersonaServiceError as error:
            raise _http_error(error) from error
        AgentRuntime.refresh_persona(name)
        return {"ok": True, "data": find(name).to_dict()}


@router.delete("/{name}")
def delete_persona(name: str):
    with AgentRuntime.lock:
        try:
            PersonaService().delete(name)
        except PersonaServiceError as error:
            raise _http_error(error) from error
        return {"ok": True, "data": {"deleted": name}}
