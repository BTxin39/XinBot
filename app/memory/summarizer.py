"""对话摘要器。

当 ChatMemory 消息数超出窗口上限时，在丢弃旧消息前先把它们压缩成
一段运行摘要（Running Summary），注入回系统 prompt，让 Agent 即使
超出上下文窗口也能"记住"之前的对话。

与 MemoryExtractor 的区别：
  - MemoryExtractor → 提取用户档案（结构化 JSON，永久存储）
  - ContextSummarizer → 压缩对话内容（纯文本，本次会话有效）

设计原则：
  - 增量摘要：传入已有摘要 + 新消息 → 输出合并后的摘要
  - 纯文本输出（不要求 JSON）：摘要直接注入 system prompt，不需要结构化
  - 调用时机：ChatMemory 裁剪消息前自动触发（每 20 条触发一次）
"""

from app.llm.client import LLMClient

SUMMARIZE_SYSTEM_PROMPT = """\
你是一个对话摘要器。你的任务是将对话历史压缩成一段简洁的摘要，\
帮助 AI 助手在上下文窗口有限的情况下记住之前的对话内容。

摘要要求：
1. 记录用户正在进行什么任务、开发什么项目
2. 记录用户做出的重要决定和偏好
3. 记录对话中提到但尚未解决的关键问题
4. 忽略问候、闲聊等不重要的内容
5. 用一段连续的中文表述，不超过 150 字
6. 只输出摘要文本，不要加任何前缀、后缀或解释
"""


class ContextSummarizer:
    """对话上下文摘要器。

    使用方式：
        summarizer = ContextSummarizer(llm_client)
        new_summary = summarizer.summarize(old_messages, existing_summary)
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def summarize(
        self,
        old_messages: list[dict],
        existing_summary: str = "",
    ) -> str:
        """将旧消息压缩成摘要。

        支持增量摘要：如果已有摘要，会把新消息合并进去。

        Args:
            old_messages: 即将被丢弃的消息列表
            existing_summary: 已有的运行摘要（第一次调用时为空字符串）

        Returns:
            更新后的摘要文本。如果 old_messages 为空，返回 existing_summary 不变。
        """
        if not old_messages:
            return existing_summary

        # 格式化要被摘要的消息
        formatted = "\n".join(
            f"[{m.get('role', '?')}]: {m.get('content', '') or '(tool call)'}"
            for m in old_messages
        )

        # 构造 user prompt
        if existing_summary:
            user_prompt = (
                f"已有的对话摘要：\n{existing_summary}\n\n"
                f"新的对话内容（需要合并进摘要）：\n{formatted}"
            )
        else:
            user_prompt = f"请为以下对话生成摘要：\n{formatted}"

        try:
            response = self.llm.chat(
                messages=[
                    {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            return (response.content or "").strip()
        except Exception:
            # LLM 调用失败时不阻塞对话，返回旧摘要保持降级运行
            return existing_summary
