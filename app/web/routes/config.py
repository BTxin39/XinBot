from dataclasses import asdict
from fastapi import APIRouter, HTTPException
from app.config.runtime import RuntimeConfig
from app.core.persona import PersonaStore
from app.llm.registry import LLMRegistry
from app.web.agent_manager import AgentManager
from app.web.schemas import ConfigUpdateRequest

router = APIRouter()


def public_config(config):
    data = asdict(config)
    data.pop("web_search_api_key", None)
    data.pop("mcp_servers", None)
    return data


@router.get("/api/config")
def get_config():
    return {"ok": True, "data": public_config(RuntimeConfig.load())}


@router.post("/api/config")
def update_config(body: ConfigUpdateRequest):
    with AgentManager.lock:
        config = RuntimeConfig.load()
        previous_persona = config.persona_name
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(config, key, value)
        registry = LLMRegistry()
        model = registry.get_model(config.model_name)
        if not model or model.provider != config.provider:
            raise HTTPException(422, "请选择已注册的模型和对应服务商")
        if not PersonaStore.get().get_persona(config.persona_name):
            raise HTTPException(422, "角色不存在")
        if config.persona_name != previous_persona:
            config.current_memory_name = f"web-{config.persona_name}"
        config.save()
        AgentManager.shutdown()
        return {"ok": True, "data": public_config(config)}
