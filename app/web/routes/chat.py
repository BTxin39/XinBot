import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from app.web.agent_manager import AgentManager
from app.web.schemas import ChatRequest

router = APIRouter()


def perform_chat(message):
    with AgentManager.lock:
        return AgentManager.chat(message)


@router.get("/api/chat/history")
def history():
    with AgentManager.lock:
        messages = AgentManager.get().memory.get_message()
        return {"ok": True, "data": [{"role": item["role"], "content": item.get("content") or ""}
                                     for item in messages if item["role"] in ("user", "assistant") and not item.get("tool_calls")]}


@router.delete("/api/chat/history")
def clear_history():
    with AgentManager.lock:
        agent = AgentManager.get()
        agent.memory.clear()
        if agent.persona:
            greeting = agent.persona.character_card.get("data", {}).get("first_mes", "")
            if greeting:
                agent.memory.add_message(role="assistant", content=agent.persona.render_macros(greeting))
        AgentManager._latest_message = ""
    return {"ok": True, "data": {}}


@router.post("/api/chat")
def chat(body: ChatRequest):
    return {"ok": True, "data": {"reply": perform_chat(body.message)}}


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
                reply = await run_in_threadpool(perform_chat, body.message)
                await ws.send_json({"chunk": reply})
                await ws.send_json({"done": True})
            except (ValueError, TypeError):
                await ws.send_json({"error": "消息格式不正确，或模型配置不完整"})
            except Exception:
                await ws.send_json({"error": "对话失败，请检查模型连接和密钥"})
    except WebSocketDisconnect:
        pass
