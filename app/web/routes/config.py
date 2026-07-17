"""GET/POST /api/config —— 配置读写。"""

from dataclasses import asdict
from fastapi import APIRouter
from app.config.runtime import RuntimeConfig
from app.web.agent_manager import AgentManager
from app.web.schemas import OkResponse, ErrorResponse, ConfigData, ConfigUpdateRequest

router = APIRouter()


@router.get("/api/config", response_model=OkResponse)
async def get_config():
    try:
        config = RuntimeConfig.load()
        return OkResponse(data=ConfigData(**asdict(config)).model_dump())
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.post("/api/config", response_model=OkResponse)
async def update_config(req: ConfigUpdateRequest):
    try:
        config = RuntimeConfig.load()
        updates = req.model_dump(exclude_none=True)
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
        config.save()
        AgentManager.reload()
        return OkResponse(data=ConfigData(**asdict(config)).model_dump())
    except Exception as e:
        return ErrorResponse(error=str(e))
