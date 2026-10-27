"""提醒管理接口（`/api/reminders`）。

提醒的**投递**不在这里——它由 `/api/pet/state` 在桌宠轮询时逐条发出，
这样"到点提醒"不需要额外的推送通道，也不会在没人看的页面里空转。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.interfaces.web.schemas import ErrorResponse, OkResponse
from app.services import reminder_service

router = APIRouter(prefix="/api")


class ReminderCreate(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    at: str = Field(min_length=1, max_length=40)
    repeat: str = Field(default="once", max_length=10)


class ReminderToggle(BaseModel):
    enabled: bool


def _serialize(item) -> dict:
    return {
        "id": item.id,
        "text": item.text,
        "at": item.at,
        "repeat": item.repeat,
        "enabled": item.enabled,
        "fired": item.fired,
        "last_fired_date": item.last_fired_date,
    }


@router.get("/reminders", response_model=OkResponse | ErrorResponse)
def list_reminders():
    try:
        book = reminder_service.book()
        return OkResponse(data={
            "items": [_serialize(item) for item in book.all()],
            "state": book.state(),
        })
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.post("/reminders", response_model=OkResponse | ErrorResponse)
def create_reminder(body: ReminderCreate):
    try:
        book = reminder_service.book()
        item = book.add(body.text, body.at, body.repeat)
        return OkResponse(data={"item": _serialize(item), "state": book.state()})
    except ValueError as error:  # 校验失败是用户输入问题，不该报 500
        return ErrorResponse(error=str(error))
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.delete("/reminders/{reminder_id}", response_model=OkResponse | ErrorResponse)
def delete_reminder(reminder_id: str):
    try:
        removed = reminder_service.book().remove(reminder_id)
        return OkResponse(data={"removed": removed})
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.put("/reminders/{reminder_id}", response_model=OkResponse | ErrorResponse)
def toggle_reminder(reminder_id: str, body: ReminderToggle):
    try:
        changed = reminder_service.book().toggle(reminder_id, body.enabled)
        return OkResponse(data={"changed": changed})
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.delete("/reminders", response_model=OkResponse | ErrorResponse)
def clear_reminders():
    try:
        count = reminder_service.book().clear()
        return OkResponse(data={"cleared": count})
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))
