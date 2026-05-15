from openai import OpenAI
from app.config.settings import Settings
from app.llm.schemas import ChatResponse

class LLMClient:
    def __init__(self):
        # self.config = RuntimeConfig()
        self.client = OpenAI(
            api_key = Settings.OPENAI_API_KEY,
            base_url = Settings.BASE_URL  # 添加基础URL配置
        )

    # DEPRECATED    
    def chat(
            self,
            messages: list[dict],
            model: str,
            temperature: float
    ) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature
        )

        return ChatResponse(
            content=(
                response.choices[0].message.content
            ),
            prompt_tokens=(
                response.usage.prompt_tokens
            ),
            completion_tokens=(
                response.usage.completion_tokens
            ),
            total_tokens=(
                response.usage.total_tokens
            )
        )
        
    def stream_chat(
            self,
            messages: list[dict],
            model: str,
            temperature: str
    ):
        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True
        )
        
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta