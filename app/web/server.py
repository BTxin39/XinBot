"""FastAPI 应用入口 —— 生命周期、CORS、路由挂载、静态文件。"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.web.agent_manager import AgentManager
from app.web.routes import status, chat, config, persona, rag, pet


STATIC_DIR = Path(__file__).parent / "static" / "dist"


@asynccontextmanager
async def lifespan(application: FastAPI):
    """启动时预热 Agent，关闭时清理资源。"""
    AgentManager.get()
    yield
    AgentManager.shutdown()


app = FastAPI(title="XinBot Web", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API 路由 ──────────────────────────────────────────────

app.include_router(status.router)
app.include_router(chat.router)
app.include_router(config.router)
app.include_router(persona.router)
app.include_router(rag.router)
app.include_router(pet.router)


# ── 静态文件（生产模式：build 产物在 static/dist/）───────

def mount_static():
    if STATIC_DIR.exists() and STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
