"""流式对话契约（v0.2.2）。

改造前 `Agent.stream_chat` 是**假流式**：`llm.chat()` 整段返回后只 yield 一次，
所以桌宠气泡要等完整回复才出现。现在改为真流式，同时保持工具调用可用。

这组测试锁住三件事：
    1. 文本确实是**多段** yield 出来的（不是一次性）；
    2. 流里的 `tool_calls` 事件不会被当成正文输出，且工具会被执行；
    3. 工具参数分片（同一 index 多次到达）必须正确合并。
"""

from types import SimpleNamespace

import pytest

from app.config.runtime import RuntimeConfig
from app.llm.schemas import StreamEvent
from app.llm.providers.openai_provider import OpenAIProvider


class FakeLLM:
    """按脚本逐条吐 StreamEvent 的假 LLM。

    每个元素是一个"轮次"，元素内部是该轮的 event 列表。
    """

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls = 0

    def stream_chat(self, messages=None, tools=None, model=None, temperature=None):
        self.calls += 1
        events = self.rounds.pop(0) if self.rounds else []
        yield from events

    def chat(self, *args, **kwargs):  # 真流式后不应再被调用
        raise AssertionError("不应该走非流式路径")


class FakeToolManager:
    def __init__(self):
        self.executed = []

    def execute(self, tool_calls):
        self.executed.append(tool_calls)
        return [
            {"role": "tool", "tool_call_id": call["id"], "content": "结果"}
            for call in tool_calls
        ]


@pytest.fixture
def make_agent(tmp_path, monkeypatch):
    """构造一个不碰真实模型/数据库的 Agent。"""
    import app.core.agent as agent_module

    monkeypatch.setattr(agent_module, "MAX_TOOL_ITERATIONS", 3, raising=False)
    # 绕过启动校验：这里用假模型名，不注册真实 provider
    monkeypatch.setattr(agent_module, "validate_config", lambda config: None, raising=False)

    def build(rounds):
        config = RuntimeConfig(db_path=str(tmp_path / "m.db"), model_name="fake")
        agent = agent_module.Agent(config=config)
        agent.llm = FakeLLM(rounds)
        agent.tool_manager = FakeToolManager()
        # 避免真实记忆写入
        agent.memory.add_message = lambda **kwargs: None
        return agent

    return build


def test_streams_multiple_chunks(make_agent):
    """核心断言：多段 yield，而不是一整段。"""
    agent = make_agent([[
        StreamEvent.delta("你"),
        StreamEvent.delta("好"),
        StreamEvent.delta("呀"),
    ]])
    chunks = list(agent.stream_chat("hi"))
    assert chunks == ["你", "好", "呀"], f"应当是逐段流出，实际 {chunks}"
    assert "".join(chunks) == "你好呀"


def test_single_chunk_when_model_returns_one_piece(make_agent):
    agent = make_agent([[StreamEvent.delta("完整回复")]])
    assert list(agent.stream_chat("hi")) == ["完整回复"]


def test_tool_calls_are_not_printed_as_text(make_agent):
    """工具事件不能变成正文——否则用户会看到 JSON 参数。

    注意：单轮纯文本时 `stream_chat` 会在 yield 完后直接 return（正确行为），
    所以这里必须带上工具事件，才会进入第二轮。
    """
    tool_event = StreamEvent.tools(
        [{"id": "c1", "type": "function",
          "function": {"name": "echo", "arguments": '{"text":"hi"}'}}]
    )
    agent = make_agent([
        [StreamEvent.delta("我查一下"), tool_event],
        [StreamEvent.delta("查到了")],
    ])
    chunks = list(agent.stream_chat("查天气"))
    assert chunks == ["我查一下", "查到了"]
    for chunk in chunks:
        assert "{" not in chunk and "echo" not in chunk


def test_tool_call_round_executes_then_continues(make_agent):
    tool_event = StreamEvent.tools(
        [{"id": "call-1", "type": "function",
          "function": {"name": "echo", "arguments": '{"text":"hi"}'}}]
    )
    agent = make_agent([
        [StreamEvent.delta("稍等"), tool_event],
        [StreamEvent.delta("完成了")],
    ])
    chunks = list(agent.stream_chat("帮我回显"))
    assert chunks == ["稍等", "完成了"]
    # 工具被执行了一次
    assert len(agent.tool_manager.executed) == 1
    assert agent.tool_manager.executed[0][0]["function"]["name"] == "echo"
    # 两轮都发生了
    assert agent.llm.calls == 2


def test_no_more_than_max_iterations(make_agent):
    """模型无限要求调用工具时，必须在上限处停下并给出提示。"""
    tool_event = StreamEvent.tools(
        [{"id": "c", "type": "function", "function": {"name": "loop", "arguments": "{}"}}]
    )
    agent = make_agent([[tool_event], [tool_event], [tool_event]])
    chunks = list(agent.stream_chat("hi"))
    assert any("最大工具调用次数" in chunk for chunk in chunks)


# ── provider 层：工具参数分片合并 ────────────────────────────────


def _chunk(content=None, tool_calls=None, reasoning=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls,
                            reasoning_content=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _tool_fragment(index, id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index, id=id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def test_provider_merges_split_tool_arguments():
    """同一 index 的参数会分多片到达，必须拼成一个完整 JSON。"""
    provider = OpenAIProvider.__new__(OpenAIProvider)  # 不跑 __init__（避免联网）
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: iter([
                    _chunk(tool_calls=[_tool_fragment(0, id="c1", name="echo", arguments='{"te')]),
                    _chunk(tool_calls=[_tool_fragment(0, arguments='xt":"hi"}')]),
                ])
            )
        )
    )
    events = list(provider.stream_chat([{"role": "user", "content": "x"}], "m", 0.7))
    assert len(events) == 1
    assert events[0].kind == "tool_calls"
    assert events[0].tool_calls[0]["function"]["arguments"] == '{"text":"hi"}'


def test_provider_streams_text_deltas():
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: iter([_chunk(content="a"), _chunk(content="b")])
            )
        )
    )
    events = list(provider.stream_chat([{"role": "user", "content": "x"}], "m", 0.7))
    assert [e.kind for e in events] == ["delta", "delta"]
    assert "".join(e.text for e in events) == "ab"


def test_provider_passes_tools_through():
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return iter([])

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    list(provider.stream_chat(
        [{"role": "user", "content": "x"}], "m", 0.7,
        tools=[{"type": "function", "function": {"name": "echo"}}],
    ))
    assert captured.get("tools"), "tools 必须透传给底层，否则流式下工具不可用"
    assert captured.get("stream") is True
