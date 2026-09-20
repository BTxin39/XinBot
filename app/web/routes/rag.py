from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile

from app.config.runtime import RuntimeConfig
from app.rag.document import KnowledgeBase, DocumentLoader
from app.web.schemas import RagSearchRequest, RagIngestUrlRequest

router = APIRouter(prefix="/api/rag")


def knowledge():
    return KnowledgeBase(RuntimeConfig.load())


@router.get("/sources")
def list_sources():
    return {"ok": True, "data": knowledge().list_sources()}


@router.post("/ingest")
def ingest_file(file: UploadFile):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in DocumentLoader.SUPPORTED_EXTENSIONS | {".pdf"}:
        raise HTTPException(422, "不支持此文档类型")
    content = file.file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "文档不能超过 20 MB")
    kb = knowledge()
    directory = Path(kb.config.knowledge_dir) / "_uploads"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{uuid4().hex}{suffix}"
    target.write_bytes(content)
    try:
        return {"ok": True, "data": kb.ingest_file(target)}
    except Exception:
        target.unlink(missing_ok=True)
        raise


@router.post("/ingest-url")
def ingest_url(body: RagIngestUrlRequest):
    if not body.url.startswith(("https://", "http://")):
        raise HTTPException(422, "请输入 HTTP 或 HTTPS 地址")
    result = knowledge().ingest_url(body.url)
    if result.get("status", "").startswith("error"):
        raise HTTPException(422, "网页导入失败，请检查网址及知识库配置")
    return {"ok": True, "data": result}


@router.post("/search")
def search(body: RagSearchRequest):
    return {"ok": True, "data": knowledge().search(body.query)}


@router.delete("/sources/{source_id:path}")
def delete_source(source_id: str):
    return {"ok": True, "data": {"removed": knowledge().remove_source(source_id)}}


@router.delete("/clear")
def clear():
    knowledge().clear()
    return {"ok": True, "data": {}}
