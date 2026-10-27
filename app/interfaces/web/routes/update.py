"""更新检查接口（`/api/update`）。

只读本地清单，不在服务端发起网络请求：
更新检查必须是**用户显式触发**的动作，后台悄悄联网既不可预期也不好排查。
"""

from fastapi import APIRouter

from app.interfaces.web.schemas import ErrorResponse, OkResponse
from app.paths import repo_root
from app.services import update_service

router = APIRouter(prefix="/api")

MANIFEST_NAME = "update.json"


def manifest_path() -> "object":
    """清单位置：`data/update.json`。抽成函数便于测试替换。"""
    return repo_root() / "data" / MANIFEST_NAME


@router.get("/update", response_model=OkResponse | ErrorResponse)
def update_status():
    try:
        current = update_service.current_version()
        path = manifest_path()
        manifest = update_service.load_manifest(path) if path.is_file() else None
        info = update_service.check(current, manifest)
        return OkResponse(data={
            "current": current,
            "manifest": str(path),
            "manifest_present": path.is_file(),
            "manifest_valid": manifest is not None,
            "update": None if info is None else info.as_dict(),
        })
    except Exception as error:  # noqa: BLE001
        return ErrorResponse(error=str(error))
