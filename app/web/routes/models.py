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

from dotenv import set_key
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field, HttpUrl
from PIL import Image

from app.config.runtime import RuntimeConfig
from app.llm.registry import LLMRegistry
from app.web.agent_manager import AgentManager

router = APIRouter(prefix="/api")
ROOT = Path(__file__).resolve().parents[3]
MODEL_ROOT = ROOT / "app/web/static/models"
UPLOAD_ROOT = ROOT / "data/web_uploads/pets"


class Connection(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    base_url: HttpUrl
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(default="", max_length=4096)


@router.get("/models")
def models():
    registry = LLMRegistry()
    return {"ok": True, "data": {
        "providers": [{"name": provider.name, "base_url": provider.resolved_base_url,
                       "has_key": bool(provider.api_key)} for provider in registry.list_providers()],
        "models": [asdict(model) for model in registry.list_models()],
    }}


@router.post("/models")
def save_connection(body: Connection):
    with AgentManager.lock:
        registry = LLMRegistry()
        existing = registry.get_provider(body.name)
        key_env = existing.api_key_env if existing else f"XINBOT_{body.name.upper().replace('-', '_')}_API_KEY"
        model = registry.get_model(body.model)
        if model and model.provider != body.name:
            raise HTTPException(409, "模型名称已属于其他服务商")
        if not body.api_key.strip() and not (existing and existing.api_key):
            raise HTTPException(422, "请输入 API 密钥")
        if body.api_key.strip():
            set_key(str(ROOT / ".env"), key_env, body.api_key.strip())
            os.environ[key_env] = body.api_key.strip()
        registry.data["providers"] = [item for item in registry.data.get("providers", []) if item["name"] != body.name]
        registry.data["providers"].append({"name": body.name, "provider_type": "openai-compatible",
                                           "api_key_env": key_env, "base_url": str(body.base_url)})
        if not model:
            registry.data.setdefault("models", []).append({"name": body.model, "provider": body.name})
        registry.save()
        AgentManager.shutdown()
    return models()


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
