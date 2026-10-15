"""运行配置 REST 接口 —— 只做协议转换，业务校验在 `app/services/llm_config_service.py`。

P4 变更（docs/DECISIONS_V0.2.md §5.2、D2）：
    "允许改哪些字段"的策略原先只存在于本端 schema，现收敛为
    `llm_config_service.CONFIG_UPDATE_FIELDS`，CLI 与 Web 共用同一份定义。
    角色-记忆绑定也改为调用 service 中的同一命名规则（D1 的唯一来源）。

本文件不再 import `LLMRegistry` / `PersonaStore`（依赖纪律 R3）。
"""

from fastapi import APIRouter, HTTPException

from app.services.agent_runtime import AgentRuntime
from app.services.llm_config_service import LLMConfigError, LLMConfigService
from app.interfaces.web.schemas import ConfigUpdateRequest

router = APIRouter()


def _http_error(error: LLMConfigError) -> HTTPException:
    status = {"missing": 404, "conflict": 409}.get(error.code, 422)
    return HTTPException(status, str(error))


@router.get("/api/config")
def get_config():
    return {"ok": True, "data": LLMConfigService().public_config()}


@router.post("/api/config")
def update_config(body: ConfigUpdateRequest):
    with AgentRuntime.lock:
        service = LLMConfigService()
        try:
            config = service.apply_updates(body.model_dump(exclude_none=True))
        except LLMConfigError as error:
            raise _http_error(error) from error
        AgentRuntime.rebuild()
        return {"ok": True, "data": service.public_config(config)}
