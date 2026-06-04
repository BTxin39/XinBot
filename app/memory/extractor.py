import json
import re

from app.llm.client import LLMClient
from app.memory.profile import MemoryProfile

SYSTEM_PROMPT = """\
你是一个信息提取器。你的任务是从对话中提取关于用户的关键信息，更新到已有的用户档案中。

规则：
1. 只记录长期有效的稳定信息（姓名、偏好、事实、身份等），不记录临时的闲聊内容
2. 如果新对话与已有信息冲突，以新对话为准
3. 如果新对话没有提供某类信息，保持该字段不变
4. relationship_stage 取值：new（初次见面）、familiar（比较熟悉）、close（很亲近）
5. conversation_summary 用一两句话总结最近的对话主题和要点

输出格式：严格只输出一个 JSON 对象，不要有任何其他文本、注释或 markdown 标记。
JSON 字段：user_name(nullable), user_preferences(dict), key_facts(list), relationship_stage, conversation_summary
"""


def _extract_json_from_text(text: str) -> str:
    """从 LLM 返回的文本中提取 JSON 对象。

    处理 LLM 可能返回的各种格式：
    - 纯 JSON: {"user_name": "..."}
    - Markdown 代码块: ```json ... ```
    - 代码块前后有额外文字
    """
    text = text.strip()

    # 1. 尝试匹配 ```json ... ``` 或 ``` ... ```
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block_match:
        text = code_block_match.group(1).strip()

    # 2. 尝试找到第一个 { 到最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return text


class MemoryExtractor:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def extract(
        self,
        current_profile: MemoryProfile,
        messages: list[dict],
    ) -> MemoryProfile:
        # 只取 user 和 assistant 的消息
        user_assistant_msgs = [
            m for m in messages if m.get("role") in ("user", "assistant")
        ]
        if not user_assistant_msgs:
            return current_profile

        # 格式化对话记录
        formatted = "\n".join(
            f"[{m['role']}]: {m.get('content', '') or '(tool call)'}"
            for m in user_assistant_msgs
        )

        # 构造请求：system = 提取指令，user = 数据
        user_prompt = f"""已有的用户档案：
{json.dumps(current_profile.to_dict(), ensure_ascii=False, indent=2)}

最近的对话：
{formatted}

请输出更新后的 JSON 档案："""

        response = self.llm.chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )

        raw_content = response.content or ""

        # 提取 JSON
        try:
            json_str = _extract_json_from_text(raw_content)
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            # 解析失败时打印警告，返回旧 profile 不变
            import sys
            print(
                f"\n[MemoryExtractor] JSON 解析失败: {e}",
                file=sys.stderr,
            )
            print(
                f"[MemoryExtractor] LLM 原始返回: {raw_content[:300]}",
                file=sys.stderr,
            )
            return current_profile

        return MemoryProfile.from_dict(data)
