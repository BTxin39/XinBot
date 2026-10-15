import json
from io import BytesIO
from fastapi import UploadFile, HTTPException
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from app.interfaces.web.schemas import ChatRequest
from app.services.agent_runtime import AgentRuntime

router = APIRouter()


def perform_chat(message, thinking=False, thinking_strength=2, image=None):
    with AgentRuntime.lock:
        if not thinking and image is None:
            return AgentRuntime.chat(message)
        return AgentRuntime.chat(message, thinking=thinking, thinking_strength=thinking_strength, image=image)


@router.post("/api/chat/attachment")
def extract_attachment(file: UploadFile):
    content = file.file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "附件不能超过 2 MB")
    if file.content_type == "application/pdf" and (file.filename or "").lower().endswith(".pdf"):
        from pypdf import PdfReader
        try:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages[:30])[:20000]
        except Exception as exc:
            raise HTTPException(422, "无法解析 PDF") from exc
        if not text.strip():
            raise HTTPException(422, "PDF 不包含可提取的文本")
        return {"ok": True, "data": {"text": text}}
    raise HTTPException(422, "仅支持文本型 PDF；图片请直接在聊天框添加")


@router.get("/api/chat/history")
def history():
    with AgentRuntime.lock:
        messages = AgentRuntime.get().memory.get_message()
        return {"ok": True, "data": [{"role": item["role"], "content": item.get("content") or ""}
                                     for item in messages if item["role"] in ("user", "assistant") and not item.get("tool_calls")]}


@router.delete("/api/chat/history")
def clear_history():
    with AgentRuntime.lock:
        AgentRuntime.get().memory.clear()
        # 清空后重建，使 first_mes 问候语按统一路径重新灌入（原实现在此处重复了一份该逻辑）
        AgentRuntime.rebuild()
    return {"ok": True, "data": {}}


@router.post("/api/chat")
def chat(body: ChatRequest):
    return {"ok": True, "data": {"reply": perform_chat(body.message, body.thinking, body.thinking_strength, body.image)}}


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    if ws.headers.get("origin") and ws.headers["origin"] not in {
        f"http://{ws.headers.get('host')}", "http://localhost:5173", "http://127.0.0.1:5173"
    }:
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                body = ChatRequest.model_validate(json.loads(raw))
                reply = await run_in_threadpool(perform_chat, body.message, body.thinking, body.thinking_strength, body.image)
                await ws.send_json({"chunk": reply})
                await ws.send_json({"done": True})
            except (ValueError, TypeError):
                await ws.send_json({"error": "消息格式不正确，或模型配置不完整"})
            except Exception:
                await ws.send_json({"error": "对话失败，请检查模型连接和密钥"})
    except WebSocketDisconnect:
        pass
