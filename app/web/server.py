"""FastAPI 应用入口 —— 生命周期、CORS、路由挂载、静态文件。"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from app.web.agent_manager import AgentManager
from app.web.routes import status, chat, config, persona, rag, pet
from app.web.routes import models
from app.web.routes import memory, ascii_art
from starlette.middleware.trustedhost import TrustedHostMiddleware


STATIC_DIR = Path(__file__).parent / "static" / "dist"


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Allow setup without credentials and release the lazy agent on exit."""
    try:
        yield
    finally:
        AgentManager.shutdown()


app = FastAPI(title="XinBot Web", version="0.1.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

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
app.include_router(models.router)
app.include_router(memory.router)
app.include_router(ascii_art.router)


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({"ok": False, "error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({"ok": False, "error": "输入内容无效，请检查必填字段和数据格式"}, status_code=422)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    return JSONResponse({"ok": False, "error": "操作失败，请检查本地配置或服务日志"}, status_code=500)


@app.middleware("http")
async def local_origin(request, call_next):
    origin = request.headers.get("origin")
    allowed = {f"http://{request.headers.get('host')}", "http://localhost:5173", "http://127.0.0.1:5173"}
    if request.method not in ("GET", "HEAD", "OPTIONS") and (
        (origin and origin not in allowed) or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        return JSONResponse({"ok": False, "error": "不允许来自此来源的写入请求"}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


ROOT = Path(__file__).resolve().parents[2]
for url, directory in (("/models", Path(__file__).parent / "static/models"),
                       ("/vendor", Path(__file__).parent / "static/vendor"),
                       ("/codexpet", ROOT / "pet/codexpet"),
                       ("/media", ROOT / "data/web_uploads")):
    directory.mkdir(parents=True, exist_ok=True)
    app.mount(url, StaticFiles(directory=directory), name=url[1:])


# ── 静态文件（生产模式：build 产物在 static/dist/）───────

def mount_static():
    if STATIC_DIR.exists() and STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
