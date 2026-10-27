"""主题接口（`/api/themes`、`/api/theme`）。

前端启动时拉一次列表并应用；选择结果同时落在 `data/theme.json` 与
浏览器 localStorage——后者用于**首屏就应用**，避免闪一下默认配色。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.interfaces.web.schemas import ErrorResponse, OkResponse
from app.paths import repo_root
from app.services import theme_service

router = APIRouter(prefix="/api")


class ThemeChoice(BaseModel):
    name: str = Field(min_length=1, max_length=32)


@router.get("/themes", response_model=OkResponse | ErrorResponse)
def list_themes():
    try:
        return OkResponse(data={
            "items": theme_service.list_themes(),
            "current": theme_service.load(repo_root()),
            "default": theme_service.DEFAULT_THEME,
        })
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.get("/theme", response_model=OkResponse | ErrorResponse)
def current_theme():
    try:
        return OkResponse(data={"current": theme_service.load(repo_root())})
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))


@router.post("/theme", response_model=OkResponse | ErrorResponse)
def choose_theme(body: ThemeChoice):
    try:
        problem = theme_service.validate(body.name)
        if problem:
            return ErrorResponse(error=problem)
        saved = theme_service.save(repo_root(), body.name)
        return OkResponse(data={
            "current": saved,
            "variables": theme_service.resolve(saved).variables,
        })
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))
