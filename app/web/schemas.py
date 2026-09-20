"""Pydantic 请求/响应模型 —— 统一 API 数据格式。"""

from pydantic import BaseModel, Field


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

class RagIngestUrlRequest(BaseModel):
    url: str = Field(..., min_length=1)

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
