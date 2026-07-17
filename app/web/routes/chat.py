"""POST /api/chat + WebSocket /ws/chat —— 对话接口。"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.web.agent_manager import AgentManager
from app.web.schemas import OkResponse, ErrorResponse, ChatRequest, ChatResponse

router = APIRouter()


@router.post("/api/chat", response_model=OkResponse)
async def chat(req: ChatRequest):
    try:
        reply = AgentManager.chat(req.message)
        return OkResponse(data=ChatResponse(reply=reply).model_dump())
    except Exception as e:
        return ErrorResponse(error=str(e))


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                import json
                data = json.loads(raw)
                message = data.get("message", "")
            except Exception:
                message = raw

            if not message.strip():
                await ws.send_json({"error": "消息不能为空"})
                continue

            try:
                for chunk in AgentManager.stream_chat(message):
                    await ws.send_json({"chunk": chunk})
                await ws.send_json({"done": True})
            except Exception as e:
                await ws.send_json({"error": str(e)})
    except WebSocketDisconnect:
        pass
