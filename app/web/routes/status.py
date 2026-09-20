from fastapi import APIRouter
from app.config.runtime import RuntimeConfig
from app.config.validation import ConfigValidator
from app.web.agent_manager import AgentManager

router = APIRouter()


@router.get("/api/status")
def get_status():
    config = RuntimeConfig.load()
    agent = AgentManager._instance
    return {"ok": True, "data": {
        "emotion": agent.state.emotion if agent else "normal",
        "model_name": config.model_name, "provider": config.provider,
        "persona_name": config.persona_name,
        "ready": not ConfigValidator.validate_startup_config(config),
        "latest_message": AgentManager._latest_message,
    }}
