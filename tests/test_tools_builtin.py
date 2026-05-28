import pytest
from app.core.tools.builtin.system import GetTimeTool, SetEmotionTool, GetStatusTool


class FakeAgent:
    """Minimal fake Agent for builtin tool testing — no LLM, no config."""

    def __init__(self):
        self.emotion = "normal"

    def change_emotion(self, new_emotion: str):
        self.emotion = new_emotion

    def get_status(self):
        from app.core.schemas import AgentStatus

        return AgentStatus(
            emotion=self.emotion,
            provider="test",
            model_name="test-model",
            memory_messages=0,
        )


class TestGetTimeTool:
    def test_returns_non_empty_string(self):
        tool = GetTimeTool()
        result = tool.execute()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_schema_is_valid(self):
        tool = GetTimeTool()
        schema = tool.to_openai_schema()
        assert schema["function"]["name"] == "get_time"
        assert schema["function"]["parameters"]["properties"] == {}


class TestGetStatusTool:
    def test_returns_status_string(self):
        agent = FakeAgent()
        tool = GetStatusTool(agent)
        result = tool.execute()
        assert "normal" in result
        assert "test-model" in result
        assert "0" in result


class TestSetEmotionTool:
    def test_valid_emotion(self):
        agent = FakeAgent()
        tool = SetEmotionTool(agent)
        result = tool.execute(emotion="happy")
        assert agent.emotion == "happy"
        assert "happy" in result

    def test_invalid_emotion(self):
        agent = FakeAgent()
        tool = SetEmotionTool(agent)
        result = tool.execute(emotion="furious")
        assert agent.emotion == "normal"
        assert "无效情绪" in result

    def test_all_valid_emotions(self):
        valid = ["normal", "happy", "sad", "angry", "sleepy"]
        agent = FakeAgent()
        tool = SetEmotionTool(agent)
        for emotion in valid:
            result = tool.execute(emotion=emotion)
            assert agent.emotion == emotion

    def test_enum_in_schema(self):
        agent = FakeAgent()
        tool = SetEmotionTool(agent)
        schema = tool.to_openai_schema()
        props = schema["function"]["parameters"]["properties"]
        assert props["emotion"]["enum"] == ["normal", "happy", "sad", "angry", "sleepy"]
