import json
import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

import httpx

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field, HttpUrl
from PIL import Image

from app.paths import repo_root
from app.services.agent_runtime import AgentRuntime
from app.services.llm_config_service import (
    LLMConfigError,
    LLMConfigService,
    validate_endpoint,
)
from app.interfaces.web.credentials import credential_name, validate_secret, write_secret

router = APIRouter(prefix="/api")
ROOT = repo_root()
MODEL_ROOT = ROOT / "pet/live2d"
UPLOAD_ROOT = ROOT / "pet/imported"


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
    """保存连接（服务商 + 模型）。

    校验在 `LLMConfigService.prepare_connection()`，**密钥落盘留在本适配器**
    （只有网页侧管理 `.env`）。校验全部通过后才写密钥，避免"密钥写了但连接没存"。
    """
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
        except ValueError as error:  # validate_secret 的字符校验
            raise HTTPException(422, str(error)) from error

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
        # 连接已移除；密钥非共用时一并清除
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


def catalog(root: Path, prefix: str, category: str):
    results = []
    if not root.exists():
        return results
    for file in sorted(root.rglob("*.model3.json")):
        relative = file.relative_to(root).as_posix()
        results.append({"id": f"{category}:{relative}", "name": file.name.removesuffix(".model3.json"),
                        "type": "live2d", "url": f"{prefix}/{relative}"})
    for file in sorted(root.rglob("pet.json")):
        try:
            pet = json.loads(file.read_text(encoding="utf-8-sig"))
            sprite = (file.parent / pet["spritesheetPath"]).resolve()
            if not sprite.is_relative_to(root.resolve()) or not sprite.is_file():
                continue
            results.append({"id": f"{category}:{file.relative_to(root).as_posix()}",
                            "name": pet.get("displayName", file.parent.name), "type": "sprite",
                            "url": f"{prefix}/{sprite.relative_to(root.resolve()).as_posix()}",
                            "columns": 8, "rows": 9, "frames": [6, 8, 8, 4, 5, 8, 6, 6, 6]})
        except (ValueError, KeyError, TypeError):
            continue
    return results


@router.get("/pet/models")
def pet_models():
    assets = catalog(MODEL_ROOT, "/models", "live2d")
    assets += catalog(ROOT / "pet/codexpet", "/codexpet", "codex")
    assets += catalog(UPLOAD_ROOT, "/media/pets", "imported")
    return {"ok": True, "data": assets}


@router.post("/pet/models/import")
def import_model(file: UploadFile):
    content = file.file.read(64 * 1024 * 1024 + 1)
    if len(content) > 64 * 1024 * 1024:
        raise HTTPException(413, "模型压缩包不能超过 64 MB")
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(422, "请上传 ZIP 模型包")
    with archive, TemporaryDirectory() as temp:
        target = Path(temp).resolve()
        members = archive.infolist()
        if len(members) > 1500 or sum(item.file_size for item in members) > 256 * 1024 * 1024:
            raise HTTPException(413, "解压后模型过大")
        allowed = {".json", ".moc3", ".png", ".webp", ".jpg", ".jpeg", ".wav", ".mp3", ".txt", ".md"}
        for item in members:
            destination = (target / item.filename.replace("\\", "/")).resolve()
            if not destination.is_relative_to(target):
                raise HTTPException(422, "模型包包含无效路径")
            if item.is_dir():
                continue
            if destination.suffix.lower() not in allowed:
                raise HTTPException(422, "模型包包含不支持的文件类型")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
        assets = catalog(target, "", "preview")
        if not assets:
            raise HTTPException(422, "未找到 .model3.json 或 pet.json + 精灵图")
        for asset in assets:
            if asset["type"] == "sprite":
                try:
                    with Image.open(target / asset["url"].lstrip("/")) as picture:
                        if picture.width % 8 or picture.height % 9:
                            raise ValueError("Invalid sprite dimensions")
                        picture.verify()
                except (OSError, ValueError, Image.DecompressionBombError) as error:
                    raise HTTPException(422, "精灵图必须是有效的 8 列 9 行图片") from error
            if asset["type"] == "live2d":
                model_file = target / asset["url"].lstrip("/")
                manifest = json.loads(model_file.read_text(encoding="utf-8-sig"))
                refs = manifest.get("FileReferences", {})
                paths = [refs.get("Moc", ""), *refs.get("Textures", [])]
                if not refs.get("Textures"):
                    raise HTTPException(422, "Live2D 模型缺少纹理")
                paths.extend(refs[key] for key in ("Physics", "Pose", "DisplayInfo", "UserData") if refs.get(key))
                paths.extend(item.get("File", "") for item in refs.get("Expressions", []))
                for motions in refs.get("Motions", {}).values():
                    paths.extend(item.get("File", "") for item in motions)
                    paths.extend(item["Sound"] for item in motions if item.get("Sound"))
                for path in paths:
                    resolved = (model_file.parent / path).resolve()
                    if not path or not resolved.is_relative_to(target) or not resolved.is_file():
                        raise HTTPException(422, "Live2D 模型缺少本地模型或纹理文件")
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, UPLOAD_ROOT / uuid4().hex)
    return pet_models()
