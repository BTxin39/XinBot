"""知识库（RAG）业务编排 —— 跨端唯一入口（§5.2、P4）。

`KnowledgeBase`（`app/rag/document.py`）已是领域实现，因此本模块的职责是
把**原先散在两端、各写一份的校验与编排**收敛起来：

    - 标签校验（长度 / 非空）
    - 导入文件的大小与类型校验
    - 网址协议校验
    - 领域异常语义（供适配器翻译成 HTTP 状态码或终端提示）

文件落盘（临时文件、上传目录）留在适配器：CLI 直接用用户给的路径，
Web 从上传流写到临时文件。service 统一接收**路径**，因此两端可共享同一入口。

分层约束：本模块不得 import `fastapi` / `rich` / `typer`（R2）。
"""

from pathlib import Path

from app.config.runtime import RuntimeConfig
from app.rag.document import DocumentLoader, KnowledgeBase

# 校验常量（原分散在 app/interfaces/web/routes/rag.py，现为两端共享）
TAG_MIN_LENGTH = 1
TAG_MAX_LENGTH = 64
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
DEFAULT_TAG = "default"
ALLOWED_URL_SCHEMES = ("https://", "http://")


class RagServiceError(Exception):
    """知识库操作的领域异常。适配器负责翻译成 HTTP 状态码或终端提示。"""

    def __init__(self, message: str, code: str = "invalid"):
        self.code = code
        super().__init__(message)


def validate_tag(tag: str) -> str:
    """校验并归一化标签。"""
    normalized = (tag or "").strip()
    if len(normalized) < TAG_MIN_LENGTH or len(normalized) > TAG_MAX_LENGTH:
        raise RagServiceError(f"标签长度须为 {TAG_MIN_LENGTH}-{TAG_MAX_LENGTH} 字符")
    return normalized


def validate_upload(suffix: str, size: int | None = None) -> None:
    """校验上传文件的扩展名与大小。"""
    if suffix.lower() not in DocumentLoader.SUPPORTED_EXTENSIONS | {".pdf"}:
        raise RagServiceError("不支持此文档类型")
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise RagServiceError("文档不能超过 20 MB", code="too_large")


def validate_url(url: str) -> str:
    if not url.startswith(ALLOWED_URL_SCHEMES):
        raise RagServiceError("请输入 HTTP 或 HTTPS 地址")
    return url


class RagService:
    """知识库的查询与变更。"""

    def __init__(self, config: RuntimeConfig | None = None, knowledge=None):
        self.config = config or RuntimeConfig.load()
        self.knowledge = knowledge or KnowledgeBase(self.config)

    # ── 查询 ─────────────────────────────────────────────────

    def list_sources(self) -> list[dict]:
        return self.knowledge.list_sources()

    def search(self, query: str, k: int = 5, tags: list[str] | None = None) -> list[dict]:
        return self.knowledge.search(query, k=k, tags=tags)

    def stats(self) -> dict:
        sources = self.knowledge.list_sources()
        store_stats = self.knowledge.store.stats()
        return {
            "sources": len(sources),
            "total_chunks": store_stats["total_chunks"],
            "collection_name": store_stats["collection_name"],
        }

    def graph(self) -> dict:
        """知识源与角色的标签关联图（供 Web 可视化）。"""
        from app.core.persona import PersonaStore

        return {
            "sources": self.knowledge.list_sources(),
            "personas": [
                {
                    "name": persona.name,
                    "display_name": persona.display_name,
                    "tags": persona.knowledge_tags,
                }
                for persona in PersonaStore.get().list_personas()
            ],
        }

    # ── 导入 ─────────────────────────────────────────────────

    def upload_directory(self) -> Path:
        """Web 上传文件的暂存目录。"""
        directory = Path(self.config.knowledge_dir) / "_uploads"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def ingest_path(self, path: str | Path, tag: str = DEFAULT_TAG) -> dict:
        """导入单个文件（路径形式，CLI 与 Web 共用）。"""
        return self.knowledge.ingest_file(path, tag=validate_tag(tag))

    def ingest_directory(self, path: str | Path) -> list[dict]:
        return self.knowledge.ingest_directory(path)

    def ingest_url(self, url: str, tag: str = DEFAULT_TAG) -> dict:
        result = self.knowledge.ingest_url(validate_url(url), tag=validate_tag(tag))
        if str(result.get("status", "")).startswith("error"):
            raise RagServiceError("网页导入失败，请检查网址及知识库配置", code="upstream")
        return result

    # ── 变更 ─────────────────────────────────────────────────

    def remove_source(self, source_id: str) -> int:
        return self.knowledge.remove_source(source_id)

    def set_source_tag(self, source_id: str, tag: str) -> int:
        count = self.knowledge.set_source_tag(source_id, validate_tag(tag))
        if not count:
            raise RagServiceError("知识源不存在", code="missing")
        return count

    def clear(self) -> None:
        self.knowledge.clear()
