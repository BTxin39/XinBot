import json
import os
import re
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import zipfile
import shutil
from typing import Literal
from urllib.parse import urlsplit
import httpx

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field, HttpUrl
from PIL import Image

from app.config.runtime import RuntimeConfig
from app.llm.registry import LLMRegistry
from app.web.agent_manager import AgentManager
from app.web.credentials import credential_name, validate_secret, write_secret

router = APIRouter(prefix="/api")
ROOT = Path(__file__).resolve().parents[3]
MODEL_ROOT = ROOT / "pet/live2d"
UPLOAD_ROOT = ROOT / "pet/imported"


class Connection(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    base_url: HttpUrl
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(default="", max_length=4096)
    provider_type: Literal["openai-compatible", "ollama"] = "openai-compatible"


def validate_endpoint(url: str, local_only: bool = False):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(422, "接口地址不能包含用户名、密码、查询参数或片段")
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if local_only and not local:
        raise HTTPException(422, "Ollama 仅支持本机地址")
    if parsed.scheme not in {"http", "https"} or (parsed.scheme == "http" and not local):
        raise HTTPException(422, "远程接口必须使用 HTTPS")


@router.get("/models")
def models():
    registry = LLMRegistry()
    return {"ok": True, "data": {
        "providers": [{"name": provider.name, "base_url": provider.resolved_base_url,
                       "provider_type": provider.provider_type,
                       "has_key": bool(provider.api_key)} for provider in registry.list_providers()],
        "models": [asdict(model) for model in registry.list_models()],
    }}


@router.post("/models")
def save_connection(body: Connection):
    with AgentManager.lock:
        registry = LLMRegistry()
        existing = registry.get_provider(body.name)
        base_url = str(body.base_url).rstrip("/")
        validate_endpoint(base_url, body.provider_type == "ollama")
        if body.provider_type == "ollama":
            if not base_url.endswith("/v1"):
                base_url += "/v1"
        key_env = existing.api_key_env if existing else credential_name(body.name)
        model = registry.get_model(body.model)
        if model and model.provider != body.name:
            raise HTTPException(409, "模型名称已属于其他服务商")
        if body.api_key:
            validate_secret(body.api_key)
        if existing and existing.api_key and not body.api_key and (
            (existing.resolved_base_url or "https://api.openai.com/v1").rstrip("/") != base_url
            or existing.provider_type != body.provider_type
        ):
            raise HTTPException(409, "更改接口地址或类型时必须重新输入密钥，不能转发原有密钥")
        if body.provider_type != "ollama" and not body.api_key and not (existing and existing.api_key):
            raise HTTPException(422, "请输入 API 密钥")
        if body.api_key:
            if any(item.name != body.name and item.api_key_env == key_env for item in registry.list_providers()):
                raise HTTPException(409, "此密钥由多个连接共用，请先在本机拆分环境变量")
            write_secret(ROOT, key_env, body.api_key)
        registry.data["providers"] = [item for item in registry.data.get("providers", []) if item["name"] != body.name]
        registry.data["providers"].append({"name": body.name, "provider_type": body.provider_type,
                                           "api_key_env": key_env, "base_url": base_url})
        if not model:
            registry.data.setdefault("models", []).append({"name": body.model, "provider": body.name})
        registry.save()
        AgentManager.shutdown()
    return models()


class ModelInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=60)


@router.post("/models/register")
def register_model(body: ModelInput):
    from app.llm.registry import ModelConfig
    with AgentManager.lock:
        registry = LLMRegistry()
        if not registry.get_provider(body.provider):
            raise HTTPException(404, "连接不存在")
        registry.add_model(ModelConfig(name=body.name, provider=body.provider))
    return models()


@router.delete("/models/{name:path}")
def delete_model(name: str):
    with AgentManager.lock:
        if RuntimeConfig.load().model_name == name:
            raise HTTPException(409, "请先切换当前模型")
        registry = LLMRegistry()
        if not registry.get_model(name):
            raise HTTPException(404, "模型不存在")
        registry.remove_model(name)
    return models()


@router.delete("/providers/{name}/key")
def delete_key(name: str):
    with AgentManager.lock:
        registry = LLMRegistry()
        provider = registry.get_provider(name)
        if not provider:
            raise HTTPException(404, "连接不存在")
        if any(item.name != name and item.api_key_env == provider.api_key_env for item in registry.list_providers()):
            raise HTTPException(409, "此密钥由多个连接共用")
        write_secret(ROOT, provider.api_key_env, None)
        AgentManager.shutdown()
    return models()


class KeyInput(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)


@router.put("/providers/{name}/key")
def update_key(name: str, body: KeyInput):
    with AgentManager.lock:
        registry = LLMRegistry()
        provider = registry.get_provider(name)
        if not provider:
            raise HTTPException(404, "连接不存在")
        if any(item.name != name and item.api_key_env == provider.api_key_env for item in registry.list_providers()):
            raise HTTPException(409, "此密钥由多个连接共用")
        write_secret(ROOT, provider.api_key_env, body.api_key)
        AgentManager.shutdown()
    return models()


@router.delete("/providers/{name}")
def delete_provider(name: str):
    with AgentManager.lock:
        registry = LLMRegistry()
        if RuntimeConfig.load().provider == name or any(item.provider == name for item in registry.list_models()):
            raise HTTPException(409, "请先切换当前连接并删除其模型")
        if not registry.get_provider(name):
            raise HTTPException(404, "连接不存在")
        delete_key(name)
        registry.remove_provider(name)
    return models()


class OllamaRequest(BaseModel):
    base_url: HttpUrl = "http://127.0.0.1:11434"


@router.post("/ollama/models")
def ollama_models(body: OllamaRequest):
    endpoint = str(body.base_url).rstrip("/").removesuffix("/v1")
    validate_endpoint(endpoint, local_only=True)
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
