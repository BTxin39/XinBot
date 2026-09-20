import base64
from copy import deepcopy
from io import BytesIO
import json

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from app.core.persona import Persona


class CardData(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    creator_notes: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    alternate_greetings: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    creator: str = ""
    character_version: str = ""
    extensions: dict = Field(default_factory=dict)


def validate_card(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("角色卡必须是 JSON 对象")
    if "spec" in raw and raw["spec"] != "chara_card_v2":
        raise ValueError("目前支持 Character Card V2 和旧版角色卡")
    card = deepcopy(raw) if "spec" in raw else {"data": deepcopy(raw)}
    card["data"] = CardData.model_validate(card.get("data")).model_dump()
    card["spec"] = "chara_card_v2"
    card["spec_version"] = "2.0"
    return card


def read_card(content: bytes, filename: str) -> tuple[dict, bytes | None]:
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("角色卡不能超过 20 MB")
    avatar = None
    if filename.lower().endswith(".png"):
        try:
            picture = Image.open(BytesIO(content))
            if picture.format != "PNG":
                raise ValueError("请输入有效的 PNG 角色卡")
        except (OSError, Image.DecompressionBombError) as error:
            raise ValueError("请输入有效的 PNG 角色卡") from error
        with picture:
            picture.load()
            encoded = picture.info.get("chara")
            if not encoded:
                raise ValueError("PNG 中没有 chara 角色卡信息")
            raw = json.loads(base64.b64decode(encoded, validate=True))
            picture.thumbnail((512, 512))
            output = BytesIO()
            picture.convert("RGBA").save(output, format="PNG")
            avatar = output.getvalue()
    else:
        raw = json.loads(content.decode("utf-8-sig"))
    return validate_card(raw), avatar


def export_card(persona: Persona) -> dict:
    if persona.character_card:
        card = deepcopy(persona.character_card)
        card["data"]["name"] = persona.display_name
        return card
    return validate_card({"name": persona.display_name, "description": persona.background,
                          "personality": "、".join(persona.traits),
                          "system_prompt": "\n".join([persona.speaking_style, *persona.constraints])})
