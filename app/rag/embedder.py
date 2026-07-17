"""RAG Embedding 客户端 —— 复用 LLM provider 的 Embedding API。"""

from openai import OpenAI

from app.config.runtime import RuntimeConfig
from app.config.settings import Settings


class EmbeddingClient:
    """OpenAI-compatible Embedding API 封装。

    使用项目已配置的 LLM provider 的 embedding 端点。
    DeepSeek 和 OpenAI 都支持 embeddings.create。
    """

    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        self.client = OpenAI(
            api_key=Settings.OPENAI_API_KEY,
            base_url=Settings.OPENAI_BASE_URL or Settings.BASE_URL,
        )

    def embed(self, text: str) -> list[float]:
        """单文本嵌入。"""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入。"""
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.config.embedding_model,
            input=texts,
        )
        return [d.embedding for d in response.data]
