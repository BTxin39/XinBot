"""测试 ContextSummarizer 和 ChatMemory 裁剪集成。

ContextSummarizer 需要 LLMClient，这里用 mock 控制 LLM 返回值。
"""

from unittest.mock import Mock

import pytest
from app.memory.summarizer import ContextSummarizer, SUMMARIZE_SYSTEM_PROMPT
from app.memory.chat_memory import ChatMemory
from app.config.runtime import RuntimeConfig
from app.llm.schemas import LLMResponse


# ── Fake LLMClient ────────────────────────────────────────────────

def _make_llm_mock(return_text: str):
    """创建一个 mock LLMClient，chat() 返回指定文本。"""
    mock = Mock()
    mock.chat.return_value = LLMResponse(content=return_text)
    return mock


# ── ContextSummarizer 测试 ────────────────────────────────────────

class TestContextSummarizer:
    def test_empty_messages_returns_existing_summary(self):
        """空消息列表 → 不调 LLM，返回已有摘要不变。"""
        llm = _make_llm_mock("should not be called")
        summarizer = ContextSummarizer(llm)

        result = summarizer.summarize([], existing_summary="已有摘要")
        assert result == "已有摘要"
        llm.chat.assert_not_called()

    def test_summarize_without_existing(self):
        """无已有摘要 → 调 LLM 生成新摘要。"""
        llm = _make_llm_mock("用户讨论了 Django 项目。")
        summarizer = ContextSummarizer(llm)

        messages = [
            {"role": "user", "content": "我在写 Django"},
            {"role": "assistant", "content": "好的，Django 不错"},
        ]
        result = summarizer.summarize(messages)

        assert result == "用户讨论了 Django 项目。"
        llm.chat.assert_called_once()

    def test_summarize_with_existing_summary(self):
        """有已有摘要 → 调 LLM 做增量合并。"""
        llm = _make_llm_mock("用户正在开发 Django 项目，已选定 JWT 认证。")
        summarizer = ContextSummarizer(llm)

        messages = [
            {"role": "user", "content": "用 JWT 吧"},
        ]
        result = summarizer.summarize(
            messages,
            existing_summary="用户正在开发 Django 项目。",
        )

        assert "Django" in result
        assert "JWT" in result
        # 验证传给 LLM 的 user prompt 包含已有摘要
        call_args = llm.chat.call_args
        user_content = call_args[1]["messages"][1]["content"]
        assert "Django" in user_content

    def test_llm_call_includes_system_prompt(self):
        """验证 LLM 调用包含正确的 system prompt。"""
        llm = _make_llm_mock("摘要")
        summarizer = ContextSummarizer(llm)

        summarizer.summarize([{"role": "user", "content": "hi"}])

        call_args = llm.chat.call_args
        system_msg = call_args[1]["messages"][0]
        assert system_msg["role"] == "system"
        assert "对话摘要器" in system_msg["content"]

    def test_llm_exception_returns_existing_summary(self):
        """LLM 调用异常 → 返回已有摘要（降级运行，不崩溃）。"""
        llm = Mock()
        llm.chat.side_effect = RuntimeError("API 超时")
        summarizer = ContextSummarizer(llm)

        result = summarizer.summarize(
            [{"role": "user", "content": "test"}],
            existing_summary="之前的摘要",
        )

        assert result == "之前的摘要"  # 降级：保留旧摘要

    def test_summarize_handles_tool_call_messages(self):
        """带 tool_calls 的消息能被正确格式化。"""
        llm = _make_llm_mock("用户查询了时间。")
        summarizer = ContextSummarizer(llm)

        messages = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "get_time", "arguments": "{}"}}
            ]},
            {"role": "tool", "content": "2026-06-05 12:00:00", "tool_call_id": "x"},
            {"role": "assistant", "content": "现在是中午12点。"},
        ]
        result = summarizer.summarize(messages)

        assert result == "用户查询了时间。"

    def test_temperature_is_low(self):
        """摘要应该用低 temperature（0.2），保证输出稳定。"""
        llm = _make_llm_mock("摘要")
        summarizer = ContextSummarizer(llm)

        summarizer.summarize([{"role": "user", "content": "hi"}])

        call_args = llm.chat.call_args
        assert call_args[1]["temperature"] == 0.2


# ── ChatMemory 裁剪测试 ──────────────────────────────────────────

class TestChatMemoryTrim:
    @staticmethod
    def _fresh_memory(max_messages: int) -> ChatMemory:
        """创建一个干净的 ChatMemory，不从磁盘加载旧数据。

        用唯一的 memory_name 避免与 default_memory.json 冲突。
        """
        config = RuntimeConfig(
            max_memory_messages=max_messages,
            current_memory_name="test_trim",
        )
        memory = ChatMemory(config)
        memory.clear()
        return memory

    def test_add_message_returns_empty_when_not_trimming(self):
        """消息数未超窗口 → add_message 返回空列表。"""
        memory = self._fresh_memory(max_messages=10)

        discarded = memory.add_message(role="user", content="hello")

        assert discarded == []
        assert len(memory.get_message()) == 1

    def test_add_message_returns_discarded_when_trimming(self):
        """消息数超过窗口 → add_message 返回被丢弃的消息。"""
        memory = self._fresh_memory(max_messages=3)

        memory.add_message(role="user", content="msg1")
        memory.add_message(role="assistant", content="reply1")
        memory.add_message(role="user", content="msg2")

        # 第 4 条触发裁剪
        discarded = memory.add_message(role="assistant", content="reply2")

        assert len(discarded) == 1
        assert discarded[0]["content"] == "msg1"
        assert len(memory.get_message()) == 3
        assert memory.get_message()[0]["content"] == "reply1"

    def test_messages_preserved_after_trim(self):
        """裁剪后保留的是最旧消息之后的部分。"""
        memory = self._fresh_memory(max_messages=2)

        memory.add_message(role="user", content="old1")
        memory.add_message(role="user", content="old2")
        discarded = memory.add_message(role="user", content="new1")

        assert len(discarded) == 1
        assert discarded[0]["content"] == "old1"
        msgs = memory.get_message()
        assert len(msgs) == 2
        assert msgs[0]["content"] == "old2"
        assert msgs[1]["content"] == "new1"

    def test_exact_window_size_no_trim(self):
        """消息数恰好等于窗口上限 → 不裁剪。"""
        memory = self._fresh_memory(max_messages=3)

        memory.add_message(role="user", content="a")
        memory.add_message(role="assistant", content="b")
        result = memory.add_message(role="user", content="c")

        assert result == []
        assert len(memory.get_message()) == 3
