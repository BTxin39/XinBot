"""Persona CRUD —— 角色管理 REST 接口。"""

from fastapi import APIRouter
from app.core.persona import Persona as PersonaModel, PersonaStore
from app.web.schemas import (
    OkResponse, ErrorResponse,
    PersonaData, PersonaCreate, PersonaUpdate,
)

router = APIRouter()


def _to_data(p: PersonaModel) -> dict:
    return PersonaData(**p.to_dict()).model_dump()


@router.get("/api/persona", response_model=OkResponse)
async def list_persona():
    try:
        store = PersonaStore.get()
        personas = [_to_data(p) for p in store.list_personas()]
        return OkResponse(data=personas)
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.post("/api/persona", response_model=OkResponse)
async def create_persona(req: PersonaCreate):
    try:
        store = PersonaStore.get()
        persona = PersonaModel(
            name=req.name,
            display_name=req.display_name or req.name,
            traits=req.traits,
            speaking_style=req.speaking_style,
            background=req.background,
            constraints=req.constraints,
            builtin=False,
        )
        store.add_persona(persona)
        return OkResponse(data=_to_data(persona))
    except ValueError as e:
        return ErrorResponse(error=str(e))
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.put("/api/persona/{name}", response_model=OkResponse)
async def update_persona(name: str, req: PersonaUpdate):
    try:
        store = PersonaStore.get()
        store.update_persona(name, req.model_dump(exclude_none=True))
        updated = store.get_persona(name)
        if not updated:
            return ErrorResponse(error=f"Persona '{name}' 不存在")
        return OkResponse(data=_to_data(updated))
    except ValueError as e:
        return ErrorResponse(error=str(e))
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.delete("/api/persona/{name}", response_model=OkResponse)
async def delete_persona(name: str):
    try:
        store = PersonaStore.get()
        store.remove_persona(name)
        return OkResponse(data={"deleted": name})
    except ValueError as e:
        return ErrorResponse(error=str(e))
    except Exception as e:
        return ErrorResponse(error=str(e))
