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

    def add(self, chunks: list[str], metadatas: list[dict], ids: list[str]) -> None:
        if not chunks:
            return
        self._collection.add(documents=chunks, metadatas=metadatas, ids=ids)

    def search(self, query: str, k: int = 5) -> list[dict]:
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.query(query_texts=[query], n_results=min(k, count))

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
                })
        return items

    def remove(self, source: str) -> int:
        results = self._collection.get(where={"source": source})
        ids_to_delete = results.get("ids", [])
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)

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
