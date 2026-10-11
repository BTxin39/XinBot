"""ChromaDB 向量存储封装（延迟导入 chromadb）。"""

from pathlib import Path

CHROMA_PATH = Path("data/chroma_db")
COLLECTION_NAME = "xinbot_knowledge"

# 延迟导入
_chromadb = None
_ChromaSettings = None


def _ensure_chromadb():
    global _chromadb, _ChromaSettings
    if _chromadb is None:
        try:
            import chromadb as _c
            from chromadb.config import Settings as _s
            _chromadb = _c
            _ChromaSettings = _s
        except ImportError:
            raise ImportError(
                "RAG 功能需要 chromadb。请运行: uv pip install chromadb"
            )


class VectorStore:
    """ChromaDB 持久化向量存储。"""

    def __init__(self, persist_dir: str | None = None):
        _ensure_chromadb()
        persist_dir = persist_dir or str(CHROMA_PATH)
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = _chromadb.PersistentClient(
            path=persist_dir,
            settings=_ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._legacy_checked = False

    def _normalize_legacy_tags(self) -> None:
        if self._legacy_checked:
            return
        self._legacy_checked = True
        offset = 0
        while True:
            batch = self._collection.get(include=["metadatas"], limit=500, offset=offset)
            ids = batch.get("ids", [])
            old = [(item_id, meta or {}) for item_id, meta in zip(ids, batch.get("metadatas", [])) if "tag" not in (meta or {})]
            if old:
                self._collection.update(ids=[item_id for item_id, _ in old], metadatas=[{**meta, "tag": "default"} for _, meta in old])
            if len(ids) < 500:
                break
            offset += len(ids)

    def add(self, chunks: list[str], metadatas: list[dict], ids: list[str]) -> None:
        if not chunks:
            return
        self._collection.add(documents=chunks, metadatas=metadatas, ids=ids)

    def search(self, query: str, k: int = 5, tags: list[str] | None = None) -> list[dict]:
        count = self._collection.count()
        if count == 0:
            return []

        if tags is not None and not tags:
            return []
        if tags and "default" in tags and hasattr(self, "_legacy_checked"):
            self._normalize_legacy_tags()
        where = {"tag": {"$in": tags}} if tags else None
        results = self._collection.query(query_texts=[query], n_results=min(k, count), where=where)

        items: list[dict] = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results["distances"] else 0
                items.append({
                    "text": doc,
                    "source": meta.get("source", "unknown"),
                    "chunk_index": meta.get("chunk_index", 0),
                    "distance": dist,
                    "tag": meta.get("tag", "default"),
                })
        return items

    def remove(self, source: str) -> int:
        results = self._collection.get(where={"source": source})
        ids_to_delete = results.get("ids", [])
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)

    def set_source_tag(self, source: str, tag: str) -> int:
        items = self._collection.get(where={"source": source}, include=["metadatas"])
        ids = items.get("ids", [])
        if ids:
            self._collection.update(ids=ids, metadatas=[{**(meta or {}), "tag": tag} for meta in items["metadatas"]])
        return len(ids)

    def clear(self) -> None:
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def stats(self) -> dict:
        return {
            "total_chunks": self._collection.count(),
            "collection_name": COLLECTION_NAME,
        }

    @property
    def count(self) -> int:
        return self._collection.count()
