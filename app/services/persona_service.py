"""角色业务编排 —— 跨端唯一入口（docs/DECISIONS/DECISIONS_V0.2.0.md §5.2）。

解决的缺陷 **D1**：切换角色时"是否同时切换记忆上下文"此前只有 Web 做了
（写 `current_memory_name = web-{name}`），CLI 的 `persona set` 只改
`persona_name`，于是同一个角色在两端进入**不同的记忆空间**。

现在激活语义只有一份实现：`activate()` 同时设置角色与角色专属记忆
（命名规则见 `app.services.memory_service.memory_name_for_persona`）。

分层约束：本模块不得 import `fastapi` / `rich` / `typer`（R2）。
"""

from app.config.runtime import RuntimeConfig
from app.core.persona import Persona, PersonaStore
from app.services.memory_service import memory_name_for_persona


class PersonaServiceError(Exception):
    """角色操作的领域异常。适配器负责翻译成 HTTP 状态码或终端提示。"""

    def __init__(self, message: str, code: str = "invalid"):
        self.code = code
        super().__init__(message)


class PersonaService:
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        self.store = PersonaStore.get()

    # ── 查询 ─────────────────────────────────────────────────

    def list_personas(self) -> list[dict]:
        return [persona.to_dict() for persona in self.store.list_personas()]

    def get_persona(self, name: str) -> Persona:
        persona = self.store.get_persona(name)
        if persona is None:
            raise PersonaServiceError("角色不存在", code="missing")
        return persona

    def require(self, name: str) -> Persona:
        return self.get_persona(name)

    # ── 变更 ─────────────────────────────────────────────────

    def activate(self, name: str) -> Persona:
        """切换角色，并切换到该角色专属的记忆上下文（**D1 的唯一实现**）。

        CLI 与 Web 都调用这里；此前只有 Web 做了记忆切换。
        """
        persona = self.get_persona(name)
        config = RuntimeConfig.load()
        config.persona_name = name
        config.current_memory_name = memory_name_for_persona(name)
        config.save()
        self.config = config
        return persona

    def create(self, persona: Persona) -> Persona:
        try:
            self.store.add_persona(persona)
        except ValueError as error:
            raise PersonaServiceError(str(error), code="invalid") from error
        return persona

    def create_from_values(self, values: dict, default_name_prefix: str = "character-") -> Persona:
        """由普通字段字典创建角色。

        存在的意义：让路由层不必 import 领域类 `Persona`（依赖纪律 R3），
        同时把"名字为空则生成默认名"这一策略也收敛到 service 里。
        """
        from uuid import uuid4

        data = dict(values)
        data["name"] = data.get("name") or f"{default_name_prefix}{uuid4().hex[:12]}"
        return self.create(Persona(**data))

    def create_from_character_card(self, card: dict, display_name: str | None = None) -> Persona:
        """由角色卡（Character Card）创建角色。

        头像落盘属于 Web 适配器职责，因此不在 service 内处理。
        """
        from uuid import uuid4

        return self.create(
            Persona(
                name=f"character-{uuid4().hex[:12]}",
                display_name=display_name or card.get("data", {}).get("name", ""),
                character_card=card,
            )
        )

    def update(self, name: str, updates: dict) -> Persona:
        self.get_persona(name)
        try:
            self.store.update_persona(name, updates)
        except ValueError as error:
            raise PersonaServiceError(str(error), code="invalid") from error
        return self.get_persona(name)

    def delete(self, name: str) -> str:
        self.get_persona(name)
        if RuntimeConfig.load().persona_name == name:
            raise PersonaServiceError("请先切换到其他角色", code="active")
        try:
            self.store.remove_persona(name)
        except ValueError as error:
            raise PersonaServiceError(str(error), code="invalid") from error
        return name
