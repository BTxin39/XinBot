import pytest
from app.memory.profile import MemoryProfile


class TestMemoryProfile:
    def test_empty_profile_returns_empty_prompt(self):
        p = MemoryProfile.empty()
        assert p.to_prompt_text() == ""

    def test_profile_with_name_renders_name(self):
        p = MemoryProfile(user_name="小明")
        text = p.to_prompt_text()
        assert "小明" in text

    def test_profile_with_preferences(self):
        p = MemoryProfile(user_preferences={"咖啡": "美式", "音乐": "周杰伦"})
        text = p.to_prompt_text()
        assert "美式" in text
        assert "周杰伦" in text

    def test_profile_with_key_facts(self):
        p = MemoryProfile(key_facts=["用户是程序员", "用户在杭州"])
        text = p.to_prompt_text()
        assert "程序员" in text
        assert "杭州" in text

    def test_new_relationship_omitted(self):
        p = MemoryProfile(user_name="test", relationship_stage="new")
        text = p.to_prompt_text()
        assert "熟悉" not in text
        assert "亲近" not in text

    def test_familiar_relationship_rendered(self):
        p = MemoryProfile(relationship_stage="familiar")
        text = p.to_prompt_text()
        assert "熟悉" in text

    def test_close_relationship_rendered(self):
        p = MemoryProfile(relationship_stage="close")
        text = p.to_prompt_text()
        assert "亲近" in text

    def test_summary_rendered(self):
        p = MemoryProfile(conversation_summary="聊了关于Python的话题")
        text = p.to_prompt_text()
        assert "Python" in text

    def test_roundtrip_to_from_dict(self):
        original = MemoryProfile(
            user_name="测试用户",
            user_preferences={"主题": "暗色"},
            key_facts=["喜欢编程", "使用Windows"],
            relationship_stage="familiar",
            conversation_summary="上次聊了Agent架构",
            last_updated="2026-05-28T10:00:00",
        )
        data = original.to_dict()
        restored = MemoryProfile.from_dict(data)
        assert restored.user_name == original.user_name
        assert restored.user_preferences == original.user_preferences
        assert restored.key_facts == original.key_facts
        assert restored.relationship_stage == original.relationship_stage
        assert restored.conversation_summary == original.conversation_summary
        assert restored.last_updated == original.last_updated

    def test_from_none_dict_returns_empty(self):
        p = MemoryProfile.from_dict(None)
        assert p.user_name is None
        assert p.key_facts == []

    def test_from_empty_dict_returns_empty(self):
        p = MemoryProfile.from_dict({})
        assert p.user_name is None

    def test_touch_updates_timestamp(self):
        p = MemoryProfile.empty()
        assert p.last_updated == ""
        p.touch()
        assert p.last_updated != ""

    def test_full_profile_renders_all_sections(self):
        p = MemoryProfile(
            user_name="Alice",
            user_preferences={"编辑器": "VS Code"},
            key_facts=["全栈开发者"],
            relationship_stage="close",
            conversation_summary="上次聊了桌宠项目",
        )
        text = p.to_prompt_text()
        assert "Alice" in text
        assert "VS Code" in text
        assert "全栈开发者" in text
        assert "亲近" in text
        assert "桌宠项目" in text
