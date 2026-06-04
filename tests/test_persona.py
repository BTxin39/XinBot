import pytest
from app.core.persona import Persona, PERSONAS


class TestPersona:
    def test_to_prompt_text_includes_display_name(self):
        p = Persona(
            name="test",
            display_name="TestBot",
            background="A test bot.",
        )
        text = p.to_prompt_text()
        assert "TestBot" in text
        assert "A test bot." in text

    def test_traits_rendered(self):
        p = Persona(
            name="test",
            display_name="T",
            traits=["温柔", "幽默"],
        )
        text = p.to_prompt_text()
        assert "温柔" in text
        assert "幽默" in text

    def test_constraints_rendered(self):
        p = Persona(
            name="test",
            display_name="T",
            constraints=["不要说脏话", "回复要简短"],
        )
        text = p.to_prompt_text()
        assert "不要说脏话" in text
        assert "回复要简短" in text

    def test_speaking_style_rendered(self):
        p = Persona(
            name="test",
            display_name="T",
            speaking_style="用文言文说话",
        )
        text = p.to_prompt_text()
        assert "文言文" in text

    def test_empty_persona_minimal_text(self):
        p = Persona(name="min", display_name="Min")
        text = p.to_prompt_text()
        assert "Min" in text
        assert "性格特征" not in text


class TestBuiltinPersonas:
    def test_xin_exists(self):
        assert "xin" in PERSONAS
        assert PERSONAS["xin"].display_name == "xin"

    def test_shiro_is_tsundere(self):
        shiro = PERSONAS["shiro"]
        assert "傲娇" in shiro.traits
        assert "哼" in shiro.speaking_style

    def test_mentor_is_educational(self):
        mentor = PERSONAS["mentor"]
        assert "理性" in mentor.traits
        assert "引导" in mentor.speaking_style

    def test_all_personas_are_valid(self):
        from app.core.state import EMOTIONS

        for name, persona in PERSONAS.items():
            prompt = persona.to_prompt_text()
            assert len(prompt) > 0
            assert persona.display_name in prompt
