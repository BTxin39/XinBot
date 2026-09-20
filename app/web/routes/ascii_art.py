from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from fastapi import APIRouter, Form, HTTPException, UploadFile
from PIL import Image

from app.cli.image_to_ascii import image_to_ascii_simple, image_to_braille

router = APIRouter(prefix="/api/ascii")


@router.post("")
def convert(file: UploadFile, width: int = Form(default=60, ge=10, le=160),
            mode: Literal["ascii", "braille"] = Form(default="braille")):
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "图片不能超过 10 MB")
    with TemporaryDirectory() as directory:
        path = Path(directory) / "image"
        path.write_bytes(content)
        try:
            with Image.open(path) as picture:
                if picture.width * picture.height > 16_000_000 or picture.height / picture.width > 16:
                    raise ValueError("Image too large")
                picture.verify()
            output = (image_to_braille if mode == "braille" else image_to_ascii_simple)(str(path), width)
        except (OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(422, "图片无效、分辨率过大或宽高比不受支持")
    return {"ok": True, "data": {"text": output, "width": width, "mode": mode}}
