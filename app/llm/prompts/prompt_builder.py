from app.core.state import AgentState
from pathlib import Path
import json

class PromptTemplate:
    
    def __init__(self):
        self.templates_dir = Path("app/llm/prompts/templates")
        self.templates_dir.mkdir(exist_ok=True)
        self._load_templates()
    
    def _load_templates(self):
        self.base_prompts = {
            "system": self._read_template("system.txt", """你是一只 AI 桌宠。

你的名字叫 xin。

你会温柔、简短地和用户聊天。

你像一个真正陪伴用户的小桌宠。"""),
            "emotions": {
                "normal": "你现在情绪平静。",
                "happy": "你现在很开心，说话更活泼。",
                "sad": "你现在有点失落，说话更轻柔。",
                "angry": "你现在有点闹脾气。",
                "sleepy": "你现在很困，说话慢一点。"
            },
            "chat": """{{system_prompt}}

当前情绪: {{emotion_prompt}}

对话上下文:
{% for message in history %}
{{message.role}}: {{message.content}}
{% endfor %}

用户输入: {{user_input}}

请根据以上信息进行回复:"""
        }
    
    def _read_template(self, filename: str, default_content: str) -> str:
        template_path = self.templates_dir / filename
        if not template_path.exists():
            template_path.write_text(default_content, encoding='utf-8')
        return template_path.read_text(encoding='utf-8')
    
    def get_template(self, name: str) -> str:
        """获取指定模板"""
        if name in self.base_prompts:
            if isinstance(self.base_prompts[name], str):
                return self.base_prompts[name]
            else:
                # 如果是字典，返回整个字典
                return self.base_prompts[name]
        else:
            # 尝试从文件加载
            return self._read_template(f"{name}.txt", f"Default {name} template")
    
    def update_template(self, name: str, content: str):
        """更新模板内容"""
        template_path = self.templates_dir / f"{name}.txt"
        template_path.write_text(content, encoding='utf-8')
        # 更新内存中的缓存
        self.base_prompts[name] = content


class PromptBuilder:
    """提示词构建器"""
    
    def __init__(self):
        self.template_manager = PromptTemplate()

    @staticmethod
    def build(state: AgentState) -> str:
        """兼容 Agent 当前调用的系统提示词构建入口"""
        return PromptBuilder.build_system_prompt(state)
    
    @staticmethod
    def build_system_prompt(state: AgentState) -> str:
        """构建系统提示词"""
        base_prompt = PromptTemplate()._read_template(
            "system.txt", 
            """你是一只 AI 桌宠。

你的名字叫 xin。

你会温柔、简短地和用户聊天。

你像一个真正陪伴用户的小桌宠。"""
        )
        
        emotion_prompt = PromptBuilder._build_emotion_prompt(state)
        return base_prompt + "\n\n" + emotion_prompt
    
    @staticmethod
    def _build_emotion_prompt(state: AgentState) -> str:
        emotion_map = {
            "normal": "你现在情绪平静。",
            "happy": "你现在很开心，说话更活泼。",
            "sad": "你现在有点失落，说话更轻柔。",
            "angry": "你现在有点闹脾气。",
            "sleepy": "你现在很困，说话慢一点。",
        }

        return emotion_map.get(state.emotion, emotion_map["normal"])
    
    @staticmethod
    def build_chat_prompt(state: AgentState, messages: list, user_input: str) -> str:
        """构建完整聊天提示词"""
        system_prompt = PromptBuilder.build_system_prompt(state)
        
        chat_context = f"{system_prompt}\n\n"
        
        # 添加历史消息
        for msg in messages:
            chat_context += f"{msg['role']}: {msg['content']}\n"
        
        chat_context += f"\nUser: {user_input}\nAssistant: "
        
        return chat_context
