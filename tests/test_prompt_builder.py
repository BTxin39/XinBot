import pytest
from app.llm.prompts.prompt_builder import PromptBuilder
from app.core.state import AgentState, EMOTIONS
from app.core.persona import PERSONAS
from app.memory.profile import MemoryProfile


class TestPromptBuilder:
    def test_build_contains_persona(self):
        state = AgentState()
        prompt = PromptBuilder.build(state)
        assert "xin" in prompt
        assert "AI 桌宠" in prompt

    def test_build_contains_emotion(self):
        state = AgentState(emotion="happy")
        prompt = PromptBuilder.build(state)
        assert "愉快" in prompt or "活泼" in prompt

    def test_build_contains_profile_when_provided(self):
        state = AgentState()
        profile = MemoryProfile(
            user_name="测试用户",
            key_facts=["喜欢Python"],
        )
        prompt = PromptBuilder.build(state, profile)
        assert "测试用户" in prompt
        assert "Python" in prompt

    def test_build_no_profile_section_when_empty(self):
        state = AgentState()
        profile = MemoryProfile.empty()
        prompt = PromptBuilder.build(state, profile)
        assert "关于用户的信息" not in prompt

    def test_build_with_different_persona(self):
        state = AgentState()
        prompt = PromptBuilder.build(state, persona=PERSONAS["shiro"])
        assert "Shiro" in prompt
        assert "傲娇" in prompt
        assert "猫娘" in prompt

    def test_build_contains_tool_guidelines(self):
        state = AgentState()
        prompt = PromptBuilder.build(state)
        assert "工具" in prompt
        assert "get_time" in prompt

    def test_build_with_mentor_persona(self):
        state = AgentState()
        prompt = PromptBuilder.build(state, persona=PERSONAS["mentor"])
        assert "Senpai" in prompt
        assert "引导" in prompt

    def test_builds_for_all_emotions(self):
        for emotion_name in EMOTIONS:
            state = AgentState(emotion=emotion_name)
            prompt = PromptBuilder.build(state)
            assert len(prompt) > 0
