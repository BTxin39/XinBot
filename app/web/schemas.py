"""Pydantic 请求/响应模型 —— 统一 API 数据格式。"""

import base64
import binascii

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── 统一响应 ─────────────────────────────────────────────

class OkResponse(BaseModel):
    ok: bool = True
    data: object

class ErrorResponse(BaseModel):
    ok: bool = False
    error: str


# ── Status ───────────────────────────────────────────────

class StatusData(BaseModel):
    emotion: str
    provider: str
    model_name: str
    memory_messages: int
    persona_name: str
    latest_message: str


# ── Chat ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000, pattern=r"\S")
    thinking: bool = False
    thinking_strength: int = Field(default=2, ge=1, le=3)
    image: str | None = Field(default=None, max_length=2_800_000)

    @field_validator("image")
    @classmethod
    def validate_image(cls, value):
        if value is not None and not value.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")):
            raise ValueError("仅支持 PNG、JPEG、WebP 图片")
        if value is not None:
            try:
                base64.b64decode(value.split(",", 1)[1], validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("图片编码无效") from exc
        return value

class ChatResponse(BaseModel):
    reply: str


# ── Config ───────────────────────────────────────────────

class ConfigData(BaseModel):
    model_name: str
    temperature: float
    max_memory_messages: int
    provider: str
    current_memory_name: str
    persona_name: str
    embedding_model: str
    knowledge_dir: str
    web_search_enabled: bool
    web_search_api_key: str
    mcp_servers: list[dict]
    db_path: str

class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    web_port: int | None = Field(default=None, ge=1024, le=65535)
    web_search_enabled: bool | None = None
    model_name: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_memory_messages: int | None = Field(default=None, ge=2, le=200)
    provider: str | None = None
    persona_name: str | None = None


# ── Persona ──────────────────────────────────────────────

class PersonaData(BaseModel):
    name: str
    display_name: str
    traits: list[str]
    speaking_style: str
    background: str
    constraints: list[str]
    builtin: bool

class PersonaCreate(BaseModel):
    name: str = Field(..., min_length=1)
    display_name: str = ""
    traits: list[str] = []
    speaking_style: str = ""
    background: str = ""
    constraints: list[str] = []

class PersonaUpdate(BaseModel):
    display_name: str | None = None
    traits: list[str] | None = None
    speaking_style: str | None = None
    background: str | None = None
    constraints: list[str] | None = None


# ── RAG ──────────────────────────────────────────────────

class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    tags: list[str] | None = None

class RagIngestUrlRequest(BaseModel):
    url: str = Field(..., min_length=1)
    tag: str = Field(default="default", min_length=1, max_length=64)

class RagSourceData(BaseModel):
    source: str
    chunks: int


# ── Pet ──────────────────────────────────────────────────

class PetStateData(BaseModel):
    emotion: str
    persona_name: str
    latest_message: str
    has_new_message: bool
    timestamp: int
