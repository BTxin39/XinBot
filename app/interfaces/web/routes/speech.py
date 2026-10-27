"""语音输出接口（`/api/speech`）。

前端与 CLI 共用：CLI 在本机直接调 service，网页通过这里改状态与试听。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.interfaces.web.schemas import ErrorResponse, OkResponse
from app.paths import repo_root
from app.services import speech_service

router = APIRouter(prefix="/api")


class SpeechUpdate(BaseModel):
    enabled: bool | None = None
    rate: int | None = Field(default=None, ge=-10, le=10)
    volume: int | None = Field(default=None, ge=0, le=100)
    voice: str | None = Field(default=None, max_length=120)
    max_chars: int | None = Field(default=None, ge=20, le=500)


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.get("/speech/status", response_model=OkResponse | ErrorResponse)
def speech_status():
    try:
        return OkResponse(data=speech_service.service().status())
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.post("/speech", response_model=OkResponse | ErrorResponse)
def update_speech(body: SpeechUpdate):
    try:
        service = speech_service.service()
        changes = {key: value for key, value in body.model_dump().items() if value is not None}
        config = service.update_config(**changes)
        speech_service.save_config(repo_root(), config)
        return OkResponse(data=service.status())
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.post("/speech/test", response_model=OkResponse | ErrorResponse)
def test_speech(body: SpeakRequest):
    """试听：即使当前是关闭状态也允许试一次，否则用户没法判断要不要开。

    实现上用 `force=True` 而不是"临时打开再关掉"——后者会在关掉的瞬间
    `stop()` 清空队列，结果什么都没念出来（实测踩到）。
    """
    try:
        service = speech_service.service()
        if not service.available:
            return ErrorResponse(error="当前系统没有可用的语音引擎")
        queued = service.say(body.text, force=True)
        return OkResponse(data={"queued": queued, "status": service.status()})
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))
