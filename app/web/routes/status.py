"""GET /api/status —— Agent 状态查询。"""

from fastapi import APIRouter
from app.web.agent_manager import AgentManager
from app.web.schemas import OkResponse, ErrorResponse, StatusData

router = APIRouter()


@router.get("/api/status", response_model=OkResponse)
async def get_status():
    try:
        status = AgentManager.get_status()
        return OkResponse(data=StatusData(**status).model_dump())
    except Exception as e:
        return ErrorResponse(error=str(e))
