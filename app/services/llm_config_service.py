"""LLM 连接 / 模型 / 运行配置的业务编排 —— 跨端唯一入口（§5.2、P4）。

解决的缺陷 **D2**：`/api/config` 的"允许改哪些字段"策略只存在于 Web 的
pydantic schema 里，CLI 没有对应约束，两端校验规则不共享。
现在该策略收敛为 `CONFIG_UPDATE_FIELDS`（本模块），CLI 与 Web 共用。

同时把两处重复的编排收敛进来：
    - `app/interfaces/cli/config.py` 的 provider/model 增删与"切换当前模型/服务商"
    - `app/interfaces/web/routes/models.py` / `config.py` 的同类逻辑

**边界说明**：密钥落盘（`.env` 写入）仍留在 Web 适配器
（`app/interfaces/web/credentials.py`），因为它只服务网页侧的密钥管理，
CLI 从不写 `.env`（其 provider 靠环境变量）。但**决定"该用什么密钥环境变量"
以及"能否复用原密钥"的判断**在本模块，因为它属于业务规则。
"""

from dataclasses import asdict
from urllib.parse import urlsplit

from app.config.runtime import RuntimeConfig
from app.core.persona import PersonaStore
from app.llm.registry import LLMRegistry, ModelConfig, ProviderConfig
from app.services.memory_service import memory_name_for_persona

# 允许通过运行配置接口修改的字段白名单。
#
# 这是 D2 的唯一来源：CLI 与 Web 都必须经 `apply_updates()` 修改配置，
# 从而共享同一份"能改什么"的定义。
#
# 刻意**不含** `web_search_api_key` 与 `mcp_servers`：
# 前者是密钥，后者能启动任意子进程，均不应由运行配置接口写入。
CONFIG_UPDATE_FIELDS = (
    "model_name",
    "temperature",
    "max_memory_messages",
    "provider",
    "persona_name",
    "web_search_enabled",
    "embedding_model",
    "knowledge_dir",
    "db_path",
    "web_port",
)

# 这些字段绝不出现在对外响应里
CONFIG_SECRET_FIELDS = ("web_search_api_key", "mcp_servers")

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class LLMConfigError(Exception):
    """LLM 配置操作的领域异常。适配器负责翻译成 HTTP 状态码或终端提示。"""

    def __init__(self, message: str, code: str = "invalid"):
        self.code = code
        super().__init__(message)


# ── 纯校验函数（不依赖 registry，便于两端复用与单测） ──────────────

def validate_endpoint(url: str, local_only: bool = False) -> None:
    """校验服务商接口地址。

    规则（原实现在 `app/interfaces/web/routes/models.py`，现为两端共享）：
        - 不得含用户名 / 密码 / 查询参数 / 片段
        - 仅允许 http(s)；非本机地址必须使用 https
        - `local_only=True` 时仅允许本机（Ollama 场景）
    """
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LLMConfigError("接口地址不能包含用户名、密码、查询参数或片段")
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if local_only and not local:
        raise LLMConfigError("Ollama 仅支持本机地址")
    if parsed.scheme not in {"http", "https"} or (parsed.scheme == "http" and not local):
        raise LLMConfigError("远程接口必须使用 HTTPS")


def normalize_base_url(url: str, provider_type: str) -> str:
    """统一接口地址形式：去尾斜杠；Ollama 补 `/v1`。"""
    normalized = url.rstrip("/")
    if provider_type == "ollama" and not normalized.endswith("/v1"):
        normalized += "/v1"
    return normalized


class LLMConfigService:
    """服务商 / 模型 / 运行配置的查询与变更。"""

    def __init__(self, registry: LLMRegistry | None = None, config: RuntimeConfig | None = None):
        self.registry = registry or LLMRegistry()
        self.config = config or RuntimeConfig.load()

    # ── 查询 ─────────────────────────────────────────────────

    def public_registry(self) -> dict:
        """服务商与模型列表（不含密钥本身，只暴露"是否有密钥"）。"""
        return {
            "providers": [
                {
                    "name": provider.name,
                    "base_url": provider.resolved_base_url,
                    "provider_type": provider.provider_type,
                    "has_key": bool(provider.api_key),
                }
                for provider in self.registry.list_providers()
            ],
            "models": [asdict(model) for model in self.registry.list_models()],
        }

    def public_config(self, config: RuntimeConfig | None = None) -> dict:
        """对外配置快照（剔除密钥与 MCP 定义）。"""
        data = asdict(config or self.config)
        for field in CONFIG_SECRET_FIELDS:
            data.pop(field, None)
        return data

    def credential_env_for(self, provider_name: str) -> str | None:
        provider = self.registry.get_provider(provider_name)
        return provider.api_key_env if provider else None

    def env_name_shared_by_others(self, provider_name: str, env_name: str) -> bool:
        """该环境变量是否被其它服务商共用（共用则不允许改写）。"""
        return any(
            item.name != provider_name and item.api_key_env == env_name
            for item in self.registry.list_providers()
        )

    # ── 连接（服务商 + 模型）保存 ─────────────────────────────

    def prepare_connection(
        self,
        *,
        name: str,
        provider_type: str,
        base_url: str,
        model: str,
        api_key: str = "",
        key_env: str | None = None,
    ) -> dict:
        """校验并准备一次"保存连接"。

        不做任何写入——密钥落盘与 registry 持久化由适配器按顺序完成，
        以便在写密钥前就发现所有校验错误（避免"密钥写了但连接没存"）。
        返回适配器后续需要的信息。
        """
        existing = self.registry.get_provider(name)
        normalized = normalize_base_url(base_url, provider_type)
        validate_endpoint(normalized, local_only=(provider_type == "ollama"))

        env_name = key_env or (existing.api_key_env if existing else None)
        if env_name is None:
            raise LLMConfigError("缺少密钥环境变量名")

        model_config = self.registry.get_model(model)
        if model_config and model_config.provider != name:
            raise LLMConfigError("模型名称已属于其他服务商", code="conflict")

        existing_key = bool(existing and existing.api_key)
        if existing_key and not api_key:
            previous = (existing.resolved_base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
            if previous != normalized or existing.provider_type != provider_type:
                raise LLMConfigError(
                    "更改接口地址或类型时必须重新输入密钥，不能转发原有密钥", code="conflict"
                )

        if provider_type != "ollama" and not api_key and not existing_key:
            raise LLMConfigError("请输入 API 密钥")

        if api_key and self.env_name_shared_by_others(name, env_name):
            raise LLMConfigError("此密钥由多个连接共用，请先在本机拆分环境变量", code="conflict")

        return {
            "name": name,
            "provider_type": provider_type,
            "base_url": normalized,
            "model": model,
            "key_env": env_name,
            "needs_key_write": bool(api_key),
            "is_new_model": model_config is None,
        }

    def apply_connection(self, prepared: dict) -> None:
        """把已校验的连接写入 registry（调用方此前可能已写好密钥）。"""
        providers = [
            item
            for item in self.registry.data.get("providers", [])
            if item["name"] != prepared["name"]
        ]
        providers.append(
            {
                "name": prepared["name"],
                "provider_type": prepared["provider_type"],
                "api_key_env": prepared["key_env"],
                "base_url": prepared["base_url"],
            }
        )
        self.registry.data["providers"] = providers
        if prepared["is_new_model"]:
            self.registry.data.setdefault("models", []).append(
                {"name": prepared["model"], "provider": prepared["name"]}
            )
        self.registry.save()

    def remove_provider(self, name: str) -> None:
        if self.config.provider == name or any(
            item.provider == name for item in self.registry.list_models()
        ):
            raise LLMConfigError("请先切换当前连接并删除其模型", code="conflict")
        if not self.registry.get_provider(name):
            raise LLMConfigError("连接不存在", code="missing")
        try:
            self.registry.remove_provider(name)
        except ValueError as error:
            raise LLMConfigError(str(error), code="conflict") from error

    # ── 模型 ─────────────────────────────────────────────────

    def register_model(self, name: str, provider: str) -> None:
        if not self.registry.get_provider(provider):
            raise LLMConfigError("连接不存在", code="missing")
        try:
            self.registry.add_model(ModelConfig(name=name, provider=provider))
        except ValueError as error:
            raise LLMConfigError(str(error), code="conflict") from error

    def remove_model(self, name: str) -> None:
        if self.config.model_name == name:
            raise LLMConfigError("请先切换当前模型", code="conflict")
        if not self.registry.get_model(name):
            raise LLMConfigError("模型不存在", code="missing")
        self.registry.remove_model(name)

    def set_active_model(self, name: str) -> RuntimeConfig:
        """切换当前模型（并同步其服务商）。CLI 的 `config set-model` 与 Web 共用。"""
        model = self.registry.get_model(name)
        if model is None:
            raise LLMConfigError(f"未注册的模型: {name}", code="missing")
        self.config.model_name = name
        self.config.provider = model.provider
        self.config.save()
        return self.config

    def set_active_provider(self, name: str) -> RuntimeConfig:
        if not self.registry.get_provider(name):
            raise LLMConfigError(f"不支持的服务商: {name}", code="missing")
        self.config.provider = name
        self.config.save()
        return self.config

    def add_provider(self, provider: ProviderConfig) -> None:
        try:
            self.registry.add_provider(provider)
        except ValueError as error:
            raise LLMConfigError(str(error), code="conflict") from error

    # ── 运行配置（D2 的唯一写入口） ───────────────────────────

    def apply_updates(self, updates: dict) -> RuntimeConfig:
        """按白名单应用运行配置更新并保存。

        Args:
            updates: 字段名 → 新值；值为 None 的项被忽略（"未提供"语义）。
        Raises:
            LLMConfigError: 字段不在白名单内。
        """
        config = RuntimeConfig.load()
        previous_persona = config.persona_name

        for key, value in updates.items():
            if value is None:
                continue
            if key not in CONFIG_UPDATE_FIELDS:
                raise LLMConfigError(f"不允许修改配置项: {key}")
            setattr(config, key, value)

        model = self.registry.get_model(config.model_name)
        if not model or model.provider != config.provider:
            raise LLMConfigError("请选择已注册的模型和对应服务商")

        if not PersonaStore.get().get_persona(config.persona_name):
            raise LLMConfigError("角色不存在")

        if config.persona_name != previous_persona:
            # 与 PersonaService.activate 一致的角色-记忆绑定（D1 命名规则的唯一来源）
            config.current_memory_name = memory_name_for_persona(config.persona_name)

        config.save()
        self.config = config
        return config
