import pytest
from app.core.persona import Persona, PersonaStore


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

    def test_to_dict(self):
        p = Persona(
            name="test",
            display_name="Test",
            traits=["a", "b"],
            speaking_style="style",
            background="bg",
            constraints=["c1", "c2"],
            builtin=True,
        )
        d = p.to_dict()
        assert d["name"] == "test"
        assert d["display_name"] == "Test"
        assert d["traits"] == ["a", "b"]
        assert d["builtin"] is True


class TestPersonaStore:
    def test_loads_builtin_personas(self):
        store = PersonaStore.reload()
        assert store.get_persona("xin") is not None
        assert store.get_persona("shiro") is not None
        assert store.get_persona("mentor") is not None

    def test_xin_is_wholesome(self):
        store = PersonaStore.get()
        xin = store.get_persona("xin")
        assert xin is not None
        assert "温柔" in xin.traits
        assert xin.display_name == "xin"

    def test_shiro_is_tsundere(self):
        store = PersonaStore.get()
        shiro = store.get_persona("shiro")
        assert shiro is not None
        assert "傲娇" in shiro.traits
        assert "哼" in shiro.speaking_style

    def test_mentor_is_educational(self):
        store = PersonaStore.get()
        mentor = store.get_persona("mentor")
        assert mentor is not None
        assert "理性" in mentor.traits
        assert "引导" in mentor.speaking_style

    def test_all_personas_valid(self):
        store = PersonaStore.get()
        for p in store.list_personas():
            prompt = p.to_prompt_text()
            assert len(prompt) > 0
            assert p.display_name in prompt

    def test_list_personas_returns_all(self):
        store = PersonaStore.get()
        names = {p.name for p in store.list_personas()}
        assert "xin" in names
        assert "shiro" in names
        assert "mentor" in names

    def test_emotions_loaded(self):
        store = PersonaStore.get()
        assert len(store.emotions) >= 5
        assert store.get_emotion("normal") is not None
        e = store.get_emotion("happy")
        assert e is not None
        assert "愉快" in e.description or "活泼" in e.behavior_modifier

    def test_add_and_remove_custom_persona(self):
        store = PersonaStore.reload()
        p = Persona(
            name="__test__",
            display_name="Test",
            traits=["测试"],
            background="test bg",
            builtin=False,
        )
        store.add_persona(p)
        assert store.get_persona("__test__") is not None
        store.remove_persona("__test__")
        assert store.get_persona("__test__") is None

    def test_cannot_remove_builtin(self):
        store = PersonaStore.get()
        with pytest.raises(ValueError, match="内置"):
            store.remove_persona("xin")
