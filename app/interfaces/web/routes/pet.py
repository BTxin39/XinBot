"""桌面宠轮询端点：状态 + 待机行为。

待机调度是**懒计算**的：每次轮询时判断一次是否该主动说话，
触发后立刻记账，所以同一条只会出现一次——不需要后台线程定时器。
"""

import time

from fastapi import APIRouter

from app.interfaces.web.routes.status import get_status
from app.interfaces.web.schemas import (
    ErrorResponse,
    IdleActionData,
    OkResponse,
    PetStateData,
    ReminderData,
)
from app.services.idle_service import IdleScheduler
from app.services.interaction_service import InteractionPlanner, Reaction
from app.services import speech_service
from app.services import reminder_service
from pydantic import BaseModel, Field

router = APIRouter()

# 进程级调度器：桌宠窗口轮询时驱动它。
# 网页工作台不轮询这个端点，因此不会两边抢着消费同一条行为。
_scheduler = IdleScheduler(greeting_delay=3)
# 互动反应规划器（带冷却，防止连点刷屏）
_planner = InteractionPlanner()
_last_message_for_pet: tuple[str, int] = ("", 0)


class InteractRequest(BaseModel):
    kind: str = Field(default="tap", max_length=24)
    emotion: str = Field(default="normal", max_length=24)


def planner() -> InteractionPlanner:
    """暴露给测试替换。"""
    return _planner


def scheduler() -> IdleScheduler:
    """暴露给测试替换（也便于将来做成可配置）。"""
    return _scheduler


def reset_scheduler(**kwargs) -> IdleScheduler:
    """重建调度器（测试用；也让"重新打开桌宠"能重新问候一次）。"""
    global _scheduler
    _scheduler = IdleScheduler(**kwargs)
    return _scheduler


@router.get("/api/pet/state", response_model=OkResponse | ErrorResponse)
async def get_pet_state():
    try:
        status = get_status()["data"]
        latest = status.get("latest_message", "")
        now = int(time.time())

        global _last_message_for_pet
        has_new = bool(latest and latest != _last_message_for_pet[0])
        if has_new:
            _last_message_for_pet = (latest, now)
            # 有新的完整回复就朗读；未启用时 say() 直接返回 False，不做任何事。
            # 放在这里而不是聊天路由：语音属于"桌宠在场时"的行为，
            # 用户没开桌宠就不该突然出声。
            speech_service.service().say(latest)

        # 待机行为：每次轮询最多消费一条
        action = _scheduler.poll()

        # 提醒优先于待机搭话：用户设了提醒就该先说提醒
        reminder = reminder_service.book().take()
        if reminder is not None:
            speech_service.service().say(reminder.text)
            action = None

        return OkResponse(data=PetStateData(
            emotion=status["emotion"],
            persona_name=status["persona_name"],
            latest_message=latest,
            has_new_message=has_new,
            timestamp=now,
            idle_action=(
                IdleActionData(kind=action.kind, text=action.text, emotion=action.emotion)
                if action is not None
                else None
            ),
            reminder=(
                ReminderData(id=reminder.id, text=reminder.text, repeat=reminder.repeat)
                if reminder is not None
                else None
            ),
        ).model_dump())
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.post("/api/pet/touch", response_model=OkResponse | ErrorResponse)
async def touch_pet():
    """用户与桌宠互动：重置静默计时，避免刚点完就被搭话。"""
    try:
        _scheduler.touch()
        return OkResponse(data={"touched": True, "state": _scheduler.state()})
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.post("/api/pet/interact", response_model=OkResponse | ErrorResponse)
def interact_pet(body: InteractRequest):
    """点击/拖拽反应。

    冷却在服务端做：前端狂点也只会有节制地响应，不必两边各写一套限流。
    """
    try:
        reaction = _planner.plan(body.kind, body.emotion)
        # 任何互动都算"有交互"，重置待机计时
        _scheduler.touch()
        return OkResponse(data={
            "reaction": None if reaction is None else {
                "kind": reaction.kind,
                "bubble": reaction.bubble,
                "emotion": reaction.emotion,
                "motions": list(reaction.motions),
                "expression": reaction.expression,
                "cooldown_ms": reaction.cooldown_ms,
            }
        })
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))
