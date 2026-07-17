"""GET /api/pet/state —— 桌面宠轮询端点。"""

import time
from fastapi import APIRouter
from app.web.agent_manager import AgentManager
from app.web.schemas import OkResponse, ErrorResponse, PetStateData

router = APIRouter()
_last_message_for_pet: tuple[str, int] = ("", 0)


@router.get("/api/pet/state", response_model=OkResponse)
async def get_pet_state():
    try:
        status = AgentManager.get_status()
        latest = status.get("latest_message", "")
        now = int(time.time())

        global _last_message_for_pet
        has_new = bool(latest and latest != _last_message_for_pet[0])
        if has_new:
            _last_message_for_pet = (latest, now)

        data = PetStateData(
            emotion=status["emotion"],
            persona_name=status["persona_name"],
            latest_message=latest,
            has_new_message=has_new,
            timestamp=now,
        )
        return OkResponse(data=data.model_dump())
    except Exception as e:
        return ErrorResponse(error=str(e))
