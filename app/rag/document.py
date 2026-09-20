"""文档加载、分块与知识库管理。"""

import hashlib
import re
from pathlib import Path
from typing import Optional

from app.rag.embedder import EmbeddingClient

from app.config.runtime import RuntimeConfig


# ── Document Loader ────────────────────────────────────────────

class DocumentLoader:
    """多格式文档加载器。"""

    SUPPORTED_EXTENSIONS = {
        ".txt", ".md", ".py", ".json", ".html", ".htm",
        ".csv", ".log", ".yaml", ".yml", ".xml", ".rst",
    }

    @classmethod
    def load(cls, path: str | Path) -> str:
        """根据文件扩展名加载文档文本。"""
        path = Path(path)
        ext = path.suffix.lower()

        if ext == ".pdf":
            return cls._load_pdf(path)
        elif ext in (".html", ".htm"):
            return cls._load_html(path)
        elif ext == ".md":
            return cls._load_markdown(path)
        else:
            return path.read_text(encoding="utf-8", errors="replace")

    @classmethod
    def _load_pdf(cls, path: Path) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            texts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    texts.append(text)
            return "\n\n".join(texts)
        except ImportError:
            raise ImportError("PDF parsing requires pypdf: pip install pypdf")
        except Exception as e:
            return f"[PDF 解析失败: {e}]"

    @classmethod
    def _load_html(cls, path: Path) -> str:
        try:
            from bs4 import BeautifulSoup
            html = path.read_text(encoding="utf-8", errors="replace")
            soup = BeautifulSoup(html, "lxml")
            # 去掉 script/style
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)
        except ImportError:
            # Fallback: 简单去标签
            text = path.read_text(encoding="utf-8", errors="replace")
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"\s+", " ", text)
            return text

    @classmethod
    def _load_markdown(cls, path: Path) -> str:
        try:
            import markdown
            from bs4 import BeautifulSoup
            md_text = path.read_text(encoding="utf-8")
            html = markdown.markdown(md_text)
            soup = BeautifulSoup(html, "lxml")
            return soup.get_text(separator="\n", strip=True)
        except ImportError:
            return path.read_text(encoding="utf-8", errors="replace")


# ── Document Chunker ───────────────────────────────────────────

class DocumentChunker:
    """滑动窗口文本分块器。"""

    def __init__(self, chunk_size: int = 500, overlap: int = 100):
        if chunk_size <= 0 or not 0 <= overlap < chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        """将长文本分块。"""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            # 尝试在句子边界截断
            if end < len(text):
                last_period = max(
                    chunk.rfind("。"), chunk.rfind(". "),
                    chunk.rfind("\n"), chunk.rfind("！"),
                    chunk.rfind("？"),
                )
                if last_period > self.chunk_size // 2:
                    end = start + last_period + 1
                    chunk = text[start:end]

            chunk = chunk.strip()
            if chunk:
                chunks.append(chunk)

            if end >= len(text):
                break
            start = max(start + 1, end - self.overlap)

        return chunks


# ── Knowledge Base ─────────────────────────────────────────────

class KnowledgeBase:
    """知识库高层管理接口。

    组合 DocumentLoader + DocumentChunker + EmbeddingClient + VectorStore。
    """

    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        self.loader = DocumentLoader()
        self.chunker = DocumentChunker()
        self._embedder: EmbeddingClient | None = None
        self._store = None
        self.knowledge_dir = Path(self.config.knowledge_dir)

    @property
    def embedder(self) -> EmbeddingClient:
        if self._embedder is None:
            self._embedder = EmbeddingClient(self.config)
        return self._embedder

    @property
    def store(self):
        if self._store is None:
            from app.rag.vector_store import VectorStore
            self._store = VectorStore()
        return self._store

    # ── Ingest ──────────────────────────────────────────────

    def ingest_file(self, file_path: str | Path) -> dict:
        """导入单个文件到知识库。返回导入统计。"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        text = self.loader.load(file_path)
        if not text.strip():
            return {"file": str(file_path), "chunks": 0, "status": "empty"}

        chunks = self.chunker.chunk(text)
        if not chunks:
            return {"file": str(file_path), "chunks": 0, "status": "empty"}

        # 删除旧数据
        source_key = str(file_path.resolve())
        self.store.remove(source_key)

        # 嵌入 + 存储
        metadatas = [
            {"source": source_key, "chunk_index": i, "filename": file_path.name}
            for i in range(len(chunks))
        ]
        ids = [
            f"{self._hash(source_key)}_{i}"
            for i in range(len(chunks))
        ]

        self.store.add(
            chunks=chunks,
            metadatas=metadatas,
            ids=ids,
        )

        return {"file": str(file_path), "chunks": len(chunks), "status": "ok"}

    def ingest_directory(self, dir_path: str | Path) -> list[dict]:
        """导入整个目录的文件。"""
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"不是目录: {dir_path}")

        supported = DocumentLoader.SUPPORTED_EXTENSIONS | {".pdf"}
        results = []
        for file_path in sorted(dir_path.rglob("*")):
            if file_path.is_file() and file_path.suffix.lower() in supported:
                try:
                    result = self.ingest_file(file_path)
                    results.append(result)
                except Exception as e:
                    results.append({
                        "file": str(file_path), "chunks": 0, "status": f"error: {e}"
                    })
        return results

    def ingest_url(self, url: str) -> dict:
        """导入网页内容。"""
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (XinBot RAG Crawler)"
            })
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)

            if not text.strip():
                return {"file": url, "chunks": 0, "status": "empty"}

            chunks = self.chunker.chunk(text)
            source_key = f"url:{url}"
            self.store.remove(source_key)

            metadatas = [
                {"source": source_key, "chunk_index": i, "filename": url}
                for i in range(len(chunks))
            ]
            ids = [
                f"{self._hash(source_key)}_{i}"
                for i in range(len(chunks))
            ]
            self.store.add(chunks=chunks, metadatas=metadatas, ids=ids)

            return {"file": url, "chunks": len(chunks), "status": "ok"}

        except ImportError as e:
            raise ImportError(f"网页导入需要 requests + beautifulsoup4: {e}")
        except Exception as e:
            return {"file": url, "chunks": 0, "status": f"error: {e}"}

    # ── Query ────────────────────────────────────────────────

    def search(self, query: str, k: int = 5) -> list[dict]:
        """语义搜索知识库。"""
        if self.store.count == 0:
            return []
        return self.store.search(query, k=k)

    # ── Management ───────────────────────────────────────────

    def remove_source(self, source: str) -> int:
        """按来源路径删除。"""
        return self.store.remove(source)

    def list_sources(self) -> list[dict]:
        """列出所有知识来源及 chunk 数。"""
        # ChromaDB 的 get 可以拿到所有 metadata
        if self.store.count == 0:
            return []
        results = self.store._collection.get()
        source_counts: dict[str, int] = {}
        for meta in results.get("metadatas", []):
            src = meta.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        return [
            {"source": src, "chunks": count}
            for src, count in sorted(source_counts.items())
        ]

    def clear(self) -> None:
        """清空知识库。"""
        self.store.clear()

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()[:12]

    @property
    def count(self) -> int:
        return self.store.count

