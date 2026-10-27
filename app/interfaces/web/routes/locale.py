"""语言设置接口（`/api/locale`）。

前端启动时拉一次：拿到当前语言、可选语言列表、以及服务端文案包。
切换语言后前端立即生效，同时写回 `data/locale.json` 供下次启动使用。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.interfaces.web.schemas import ErrorResponse, OkResponse
from app.paths import repo_root
from app.services import i18n_service

router = APIRouter(prefix="/api")


class LocaleChoice(BaseModel):
    locale: str = Field(min_length=1, max_length=16)


def _payload(locale: str) -> dict:
    return {
        "current": locale,
        "available": i18n_service.available(),
        "default": i18n_service.DEFAULT_LOCALE,
        "messages": i18n_service.catalog(locale),
    }


@router.get("/locale", response_model=OkResponse | ErrorResponse)
def get_locale():
    try:
        return OkResponse(data=_payload(i18n_service.load(repo_root())))
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.post("/locale", response_model=OkResponse | ErrorResponse)
def set_locale(body: LocaleChoice):
    try:
        saved = i18n_service.save(repo_root(), body.locale)
        return OkResponse(data=_payload(saved))
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))
