from app.agent.state import AgentState
from pathlib import Path

class PromptBuilder:
    @staticmethod
    def build(state: AgentState) -> str:  # 移除多余的self参数
        base_prompt = Path(
            "app/llm/prompts/system.txt"
        ).read_text(encoding="utf-8")

        emotion_prompt = (
            PromptBuilder._build_emotion_prompt(state)
        )
        return base_prompt + "\n" + emotion_prompt
    @staticmethod
    def _build_emotion_prompt(state: AgentState) -> str:
        emotion_map = {
            "normal": "你现在情绪平静。",
            "happy": "你现在很开心，说话更活泼。",
            "sad": "你现在有点失落，说话更轻柔。",
            "angry": "你现在有点闹脾气。",
            "sleepy": "你现在很困，说话慢一点。",
        }

        return emotion_map.get(
            state.emotion,
            emotion_map["normal"],
        )