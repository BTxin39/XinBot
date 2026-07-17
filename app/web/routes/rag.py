"""RAG 知识库管理 REST 接口。"""

from pathlib import Path
from fastapi import APIRouter, UploadFile, File
from app.config.runtime import RuntimeConfig
from app.rag.document import KnowledgeBase
from app.web.schemas import (
    OkResponse, ErrorResponse,
    RagSearchRequest, RagIngestUrlRequest, RagSourceData,
)

router = APIRouter()
_kb: KnowledgeBase | None = None


def _get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase(RuntimeConfig.load())
    return _kb


@router.get("/api/rag/sources", response_model=OkResponse)
async def list_sources():
    try:
        kb = _get_kb()
        sources = kb.list_sources()
        return OkResponse(data=[RagSourceData(**s).model_dump() for s in sources])
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.post("/api/rag/ingest", response_model=OkResponse)
async def ingest_file(file: UploadFile = File(...)):
    try:
        kb = _get_kb()
        upload_dir = Path(kb.config.knowledge_dir) / "_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / file.filename
        content = await file.read()
        file_path.write_bytes(content)
        result = kb.ingest_file(str(file_path))
        return OkResponse(data=result)
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.post("/api/rag/ingest-url", response_model=OkResponse)
async def ingest_url(req: RagIngestUrlRequest):
    try:
        kb = _get_kb()
        result = kb.ingest_url(req.url)
        return OkResponse(data=result)
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.post("/api/rag/search", response_model=OkResponse)
async def search_rag(req: RagSearchRequest):
    try:
        kb = _get_kb()
        results = kb.search(req.query)
        return OkResponse(data=results)
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.delete("/api/rag/sources/{source_id}", response_model=OkResponse)
async def delete_source(source_id: str):
    try:
        kb = _get_kb()
        removed = kb.remove_source(source_id)
        return OkResponse(data={"removed": removed})
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.delete("/api/rag/clear", response_model=OkResponse)
async def clear_rag():
    try:
        kb = _get_kb()
        kb.clear()
        return OkResponse(data={"status": "cleared"})
    except Exception as e:
        return ErrorResponse(error=str(e))
