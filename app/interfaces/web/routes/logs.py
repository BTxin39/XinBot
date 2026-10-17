"""运行日志接口（`/api/logs`）—— CLI 与 Web 共用的日志来源。

CLI 是独立进程，无法读后端内存，因此统一走这里；
后端未运行时 CLI 会明确提示"后端未运行"，而不是返回空日志让人误判为"没有日志"。

导出说明：`/api/logs/export` 返回纯文本，由调用方（浏览器另存 / CLI 写文件）
决定落到哪里。选择"按需导出"而非"常开写盘"：环形缓冲适合排障窗口，
无限增长的日志文件反而需要额外的轮转与清理策略。
"""

import time

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app import logs as log_store

router = APIRouter(prefix="/api")

EXPORT_FORMAT = "%Y-%m-%d %H:%M:%S"


def _render(entries: list[dict]) -> str:
    """把日志条目渲染成可读文本（时间用完整日期，便于归档回溯）。"""
    lines = []
    for item in entries:
        stamp = time.strftime(EXPORT_FORMAT, time.localtime(item["time"]))
        lines.append(f"{stamp} | {item['level']:<7} | {item['logger']} | {item['message']}")
    return "\n".join(lines)


@router.get("/logs")
def get_logs(
    limit: int = Query(default=100, ge=1, le=500),
    level: str | None = Query(default=None, description="最低级别：DEBUG/INFO/WARNING/ERROR"),
):
    return {
        "ok": True,
        "data": {
            "status": log_store.status(),
            "entries": log_store.entries(limit=limit, min_level=level),
        },
    }


@router.get("/logs/status")
def get_log_status():
    return {"ok": True, "data": log_store.status()}


@router.get("/logs/export", response_class=PlainTextResponse)
def export_logs(
    limit: int = Query(default=500, ge=1, le=500),
    level: str | None = Query(default=None),
):
    """导出最近日志为纯文本（带完整日期，可直接归档）。"""
    entries = log_store.entries(limit=limit, min_level=level)
    status = log_store.status()
    header = (
        f"# XinBot 运行日志导出\n"
        f"# 导出时间：{time.strftime(EXPORT_FORMAT)}\n"
        f"# 记录条数：{len(entries)} / 缓冲 {status['buffered']}/{status['capacity']}\n"
        f"# 警告 {status['warnings']} 条，错误 {status['errors']} 条\n"
        f"# 格式：时间 | 级别 | logger | 内容\n\n"
    )
    return PlainTextResponse(
        header + _render(entries) + "\n",
        headers={"Content-Disposition": 'attachment; filename="xinbot-logs.log"'},
    )


@router.delete("/logs")
def clear_logs():
    log_store.reset()
    return {"ok": True, "data": {"cleared": True}}

