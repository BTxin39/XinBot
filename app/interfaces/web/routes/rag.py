"""知识库 REST 接口 —— 只做协议转换，业务校验在 `app/services/rag_service.py`。

P4 变更（docs/DECISIONS_V0.2.md §5.2）：
    校验（标签长度、文件类型与大小、网址协议）原先在本文件与 CLI 各写一份，
    现收敛到 service；本文件不再 import `PersonaStore`（`/graph` 改经 service）。
"""

from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.rag_service import RagService, RagServiceError, validate_upload
from app.interfaces.web.schemas import RagIngestUrlRequest, RagSearchRequest

router = APIRouter(prefix="/api/rag")


class SourceTag(BaseModel):
    tag: str = Field(min_length=1, max_length=64)


def knowledge() -> RagService:
    """service 构造器缝隙。

    测试可替换本函数以注入假知识库（见 `tests/test_v011.py`）。
    注意别改成换个名字 import `RagService`——那会让 monkeypatch 失效，
    因为路由绑定的是导入时的对象。
    """
    return RagService()


def _http_error(error: RagServiceError) -> HTTPException:
    status = {
        "missing": 404,
        "too_large": 413,
        "upstream": 422,
    }.get(error.code, 422)
    return HTTPException(status, str(error))


def _suffix_of(filename: str | None) -> str:
    name = filename or ""
    return ("." + name.rsplit(".", 1)[-1]) if "." in name else ""


@router.get("/sources")
def list_sources():
    return {"ok": True, "data": knowledge().list_sources()}


@router.post("/ingest")
def ingest_file(file: UploadFile, tag: str = Form("default")):
    suffix = _suffix_of(file.filename)
    content = file.file.read(20 * 1024 * 1024 + 1)
    try:
        # 一次校验类型与大小（原实现分两处、两端各写一份）
        validate_upload(suffix, len(content))
    except RagServiceError as error:
        raise _http_error(error) from error

    service = knowledge()
    target = service.upload_directory() / f"{uuid4().hex}{suffix}"
    target.write_bytes(content)
    try:
        return {"ok": True, "data": service.ingest_path(target, tag=tag)}
    except RagServiceError as error:
        target.unlink(missing_ok=True)
        raise _http_error(error) from error
    except Exception:
        target.unlink(missing_ok=True)
        raise


@router.post("/ingest-url")
def ingest_url(body: RagIngestUrlRequest):
    try:
        return {"ok": True, "data": knowledge().ingest_url(body.url, tag=body.tag)}
    except RagServiceError as error:
        raise _http_error(error) from error


@router.post("/search")
def search(body: RagSearchRequest):
    return {"ok": True, "data": knowledge().search(body.query, tags=body.tags)}


@router.put("/sources/{source_id:path}/tag")
def update_source_tag(source_id: str, body: SourceTag):
    try:
        count = knowledge().set_source_tag(source_id, body.tag)
    except RagServiceError as error:
        raise _http_error(error) from error
    return {"ok": True, "data": {"updated": count}}


@router.get("/graph")
def graph():
    return {"ok": True, "data": knowledge().graph()}


@router.delete("/sources/{source_id:path}")
def delete_source(source_id: str):
    return {"ok": True, "data": {"removed": knowledge().remove_source(source_id)}}


@router.delete("/clear")
def clear():
    knowledge().clear()
    return {"ok": True, "data": {}}
