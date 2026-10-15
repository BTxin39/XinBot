from fastapi import APIRouter
from app.config.runtime import RuntimeConfig
from app.config.validation import ConfigValidator
from app.services.agent_runtime import AgentRuntime

router = APIRouter()


@router.get("/api/status")
def get_status():
    config = RuntimeConfig.load()
    agent = AgentRuntime.instance()
    return {"ok": True, "data": {
        "emotion": agent.state.emotion if agent else "normal",
        "model_name": config.model_name, "provider": config.provider,
        "persona_name": config.persona_name,
        "ready": not ConfigValidator.validate_startup_config(config),
        "latest_message": AgentRuntime.latest_message(),
    }}
