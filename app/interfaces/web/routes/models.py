"""桌宠外观模型与 LLM 连接的接口。

外观部分只做协议转换：格式识别、校验、导入全部在
`app/services/live2d_service.py`（CLI 的 `xinbot model import` 走同一实现）。
"""

from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field, HttpUrl

from app.interfaces.web.credentials import credential_name, validate_secret, write_secret
from app.paths import repo_root
from app.services import live2d_service
from app.services.agent_runtime import AgentRuntime
from app.services.llm_config_service import (
    LLMConfigError,
    LLMConfigService,
    validate_endpoint,
)

router = APIRouter(prefix="/api")
ROOT = repo_root()

# 目录与运行时信息以 service 为准（CLI 也用同一份）
MODEL_ROOT = ROOT / "pet/live2d"
CODEXPET_ROOT = ROOT / "pet/codexpet"


# ── 外观：扫描与导入 ──────────────────────────────────────────────

def catalog(root: Path, prefix: str, category: str) -> list[dict]:
    """扫描一个目录，返回可用的外观资源。

    与 `live2d_service.catalog()` 的区别：这里额外补上前端需要的
    `id` / `url` / 精灵图参数等字段。
    """
    results: list[dict] = []
    if not root.exists():
        return results

    for manifest in sorted(root.rglob("*" + live2d_service.CUBISM3_SUFFIX)):
        results.append(_live2d_entry(manifest, root, prefix, category, "cubism3"))

    for manifest in sorted(root.rglob("*" + live2d_service.CUBISM2_SUFFIX)):
        try:
            package = live2d_service.validate(live2d_service.ModelCandidate(
                manifest=manifest, root=manifest.parent, kind="cubism2",
                name=manifest.name[: -len(live2d_service.CUBISM2_SUFFIX)],
            ))
        except live2d_service.ModelImportError:
            continue  # 目录里的旧格式条目同样要完整校验，避免列出加载必失败的
        entry = _live2d_entry(manifest, root, prefix, category, "cubism2")
        entry["name"] = package.name
        entry["warnings"] = package.warnings
        results.append(entry)

    for manifest in sorted(root.rglob(live2d_service.SPRITE_MANIFEST)):
        try:
            package = live2d_service.validate(live2d_service.ModelCandidate(
                manifest=manifest, root=manifest.parent, kind="sprite", name=manifest.parent.name
            ))
            sprite = (package.root / package.spritesheet).resolve()
            if not sprite.is_relative_to(root.resolve()) or not sprite.is_file():
                continue
        except (live2d_service.ModelImportError, KeyError, TypeError):
            continue
        results.append({
            "id": f"{category}:{manifest.relative_to(root).as_posix()}",
            "name": package.name,
            "type": "sprite",
            "format": "sprite",
            # 精灵图不需要额外运行时
            "runtime_ready": True,
            "url": f"{prefix}/{sprite.relative_to(root.resolve()).as_posix()}",
            "columns": live2d_service.SPRITE_COLUMNS,
            "rows": live2d_service.SPRITE_ROWS,
            "frames": live2d_service.SPRITE_FRAME_COUNTS,
            "_mtime": _mtime(manifest),
        })

    return results


def _mtime(manifest: Path) -> float:
    """清单文件修改时间，用于"重复导入时保留最新一份"的判断。"""
    try:
        return manifest.stat().st_mtime
    except OSError:
        return 0.0


def _live2d_entry(manifest: Path, root: Path, prefix: str, category: str, kind: str) -> dict:
    suffix = live2d_service.CUBISM3_SUFFIX if kind == "cubism3" else live2d_service.CUBISM2_SUFFIX
    relative = manifest.relative_to(root).as_posix()
    state = live2d_service.runtime_state().get(kind, {})
    return {
        "id": f"{category}:{relative}",
        "name": manifest.name[: -len(suffix)],
        "type": "live2d",
        "format": kind,
        "url": f"{prefix}/{relative}",
        # 让前端/CLI 能提前知道这个模型是否缺运行时，而不是加载时才失败
        "runtime_ready": state.get("ready", True),
        "runtime_missing": state.get("missing_hint", "") if not state.get("ready", True) else "",
        "_mtime": _mtime(manifest),
    }


def collect_models() -> list[dict]:
    assets = catalog(MODEL_ROOT, "/models", "live2d")
    assets += catalog(CODEXPET_ROOT, "/codexpet", "codex")
    assets += _dedupe(catalog(live2d_service.UPLOAD_ROOT, "/media/pets", "imported"))
    return assets


def _dedupe(assets: list[dict]) -> list[dict]:
    """同一模型被重复导入会产生多个目录：只保留最近导入的一份。

    与 `live2d_service.catalog()` 的去重规则保持一致，避免界面上出现重复条目。
    路径里带 uuid，排序不能代表新旧，因此比较清单文件的修改时间。
    """
    best: dict[tuple[str, str], dict] = {}
    for asset in assets:
        key = (asset.get("format", ""), asset["name"])
        current = best.get(key)
        if current is None or asset.get("_mtime", 0.0) > current.get("_mtime", 0.0):
            best[key] = asset
    priority = {"cubism3": 0, "cubism2": 1, "sprite": 2}
    ordered = sorted(
        best.values(), key=lambda item: (priority.get(item.get("format"), 9), item["name"])
    )
    for asset in ordered:
        asset.pop("_mtime", None)
    return ordered


@router.get("/pet/models")
def pet_models():
    return {"ok": True, "data": collect_models()}


@router.get("/pet/runtimes")
def pet_runtimes():
    """各 Live2D 版本的运行时就绪状态。"""
    return {"ok": True, "data": live2d_service.runtime_state()}


@router.post("/pet/models/import")
def import_model(file: UploadFile):
    content = file.file.read(live2d_service.MAX_ARCHIVE_BYTES + 1)
    try:
        imported = live2d_service.import_from_bytes(content)
    except live2d_service.ModelImportError as error:
        raise HTTPException(422, str(error)) from error
    # 返回导入摘要 + 刷新后的列表：前端不必再请求一次
    return {"ok": True, "data": {"model": imported, "models": collect_models()}}


class RenameInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def _model_http_error(error: live2d_service.ModelImportError) -> HTTPException:
    status = {
        "missing": 404,
        "conflict": 409,
        "invalid_name": 422,
        "invalid_path": 422,
    }.get(error.code, 422)
    return HTTPException(status, str(error))


@router.delete("/pet/models/{name:path}")
def delete_model_route(name: str):
    """删除一个已导入的模型（只动 pet/imported/ 下的内容）。"""
    try:
        result = live2d_service.remove_model(name)
    except live2d_service.ModelImportError as error:
        raise _model_http_error(error) from error
    return {"ok": True, "data": {"removed": result, "models": collect_models()}}


@router.put("/pet/models/{name:path}")
def rename_model_route(name: str, body: RenameInput):
    """重命名一个已导入的模型。"""
    try:
        result = live2d_service.rename_model(name, body.name)
    except live2d_service.ModelImportError as error:
        raise _model_http_error(error) from error
    return {"ok": True, "data": {"model": result, "models": collect_models()}}


# ── LLM 连接 ──────────────────────────────────────────────────────

class Connection(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    base_url: HttpUrl
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(default="", max_length=4096)
    provider_type: Literal["openai-compatible", "ollama"] = "openai-compatible"


def _http_error(error: LLMConfigError) -> HTTPException:
    status = {"missing": 404, "conflict": 409}.get(error.code, 422)
    return HTTPException(status, str(error))


@router.get("/models")
def models():
    return {"ok": True, "data": LLMConfigService().public_registry()}


@router.post("/models")
def save_connection(body: Connection):
    with AgentRuntime.lock:
        service = LLMConfigService()
        try:
            prepared = service.prepare_connection(
                name=body.name,
                provider_type=body.provider_type,
                base_url=str(body.base_url),
                model=body.model,
                api_key=body.api_key,
                key_env=service.credential_env_for(body.name) or credential_name(body.name),
            )
        except LLMConfigError as error:
            raise _http_error(error) from error

        if prepared["needs_key_write"]:
            try:
                validate_secret(body.api_key)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            write_secret(ROOT, prepared["key_env"], body.api_key)

        service.apply_connection(prepared)
        AgentRuntime.rebuild()
    return models()


class ModelInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=60)


@router.post("/models/register")
def register_model(body: ModelInput):
    with AgentRuntime.lock:
        try:
            LLMConfigService().register_model(body.name, body.provider)
        except LLMConfigError as error:
            raise _http_error(error) from error
    return models()


@router.delete("/models/{name:path}")
def delete_model(name: str):
    with AgentRuntime.lock:
        try:
            LLMConfigService().remove_model(name)
        except LLMConfigError as error:
            raise _http_error(error) from error
    return models()


@router.delete("/providers/{name}/key")
def delete_key(name: str):
    with AgentRuntime.lock:
        service = LLMConfigService()
        env_name = service.credential_env_for(name)
        if env_name is None:
            raise HTTPException(404, "连接不存在")
        if service.env_name_shared_by_others(name, env_name):
            raise HTTPException(409, "此密钥由多个连接共用")
        write_secret(ROOT, env_name, None)
        AgentRuntime.rebuild()
    return models()


class KeyInput(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)


@router.put("/providers/{name}/key")
def update_key(name: str, body: KeyInput):
    with AgentRuntime.lock:
        service = LLMConfigService()
        env_name = service.credential_env_for(name)
        if env_name is None:
            raise HTTPException(404, "连接不存在")
        if service.env_name_shared_by_others(name, env_name):
            raise HTTPException(409, "此密钥由多个连接共用")
        write_secret(ROOT, env_name, body.api_key)
        AgentRuntime.rebuild()
    return models()


@router.delete("/providers/{name}")
def delete_provider(name: str):
    with AgentRuntime.lock:
        service = LLMConfigService()
        env_name = service.credential_env_for(name)
        shared = env_name is not None and service.env_name_shared_by_others(name, env_name)
        try:
            service.remove_provider(name)
        except LLMConfigError as error:
            raise _http_error(error) from error
        if env_name and not shared:
            write_secret(ROOT, env_name, None)
    return models()


class OllamaRequest(BaseModel):
    base_url: HttpUrl = "http://127.0.0.1:11434"


@router.post("/ollama/models")
def ollama_models(body: OllamaRequest):
    endpoint = str(body.base_url).rstrip("/").removesuffix("/v1")
    try:
        validate_endpoint(endpoint, local_only=True)
    except LLMConfigError as error:
        raise _http_error(error) from error
    try:
        with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
            response = client.get(endpoint + "/api/tags")
            response.raise_for_status()
            data = response.json()
        return {"ok": True, "data": [{"name": item["name"], "size": item.get("size", 0)} for item in data["models"]]}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "无法连接 Ollama，请确认本机服务已启动")

