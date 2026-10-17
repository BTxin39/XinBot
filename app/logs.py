"""运行日志：进程内环形缓冲 + 标准 logging 接入。

需求：CLI 端与 Web 端都能看到**同一个后端**的运行状态与日志。
实现要点：

1. 后端进程是日志的唯一来源。`LogBuffer` 挂在根 logger 上，
   捕获本项目模块与 `uvicorn` 的日志。
2. Web 端直接读本进程缓冲（`/api/logs`）。
3. CLI 端是**另一个进程**，因此不能直接读内存——它通过
   `/api/logs` 拉取，并且在后端未运行时给出明确提示而不是空列表。

为什么用环形缓冲而不是写文件：
    本地单机应用，用户不一定会去翻日志文件；而"运行状态"需要的是
    最近一段时间的窗口，无限增长的日志文件反而需要另外的轮转策略。
    缓冲区有上限（默认 500 条），内存占用可控。
"""

import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field

DEFAULT_CAPACITY = 500
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


@dataclass
class LogEntry:
    time: float
    level: str
    logger: str
    message: str

    @property
    def stamp(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime(self.time))


@dataclass
class _State:
    buffer: deque = field(default_factory=lambda: deque(maxlen=DEFAULT_CAPACITY))
    lock: threading.Lock = field(default_factory=threading.Lock)
    installed: bool = False
    server_started_at: float = 0.0
    counters: dict = field(default_factory=lambda: {"warnings": 0, "errors": 0})


_state = _State()


class BufferHandler(logging.Handler):
    """把日志记录写入环形缓冲。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # 格式化失败不能影响主流程
            message = str(record.msg)

        # 异常必须带上堆栈：否则 UI 里只剩一句 "Exception in ASGI application"，
        # 完全无法定位（v0.2.1 排查一个 500 时正是被这一点卡住）。
        if record.exc_info:
            message = f"{message}\n{self.format_exception(record)}"
        elif record.exc_text:
            message = f"{message}\n{record.exc_text}"

        entry = LogEntry(
            time=record.created,
            level=record.levelname,
            logger=record.name,
            message=message,
        )
        with _state.lock:
            _state.buffer.append(entry)
            if record.levelno >= logging.ERROR:
                _state.counters["errors"] += 1
            elif record.levelno >= logging.WARNING:
                _state.counters["warnings"] += 1

    @staticmethod
    def format_exception(record: logging.LogRecord) -> str:
        """把 exc_info 渲染成紧凑堆栈（保留本项目帧，便于定位）。"""
        import traceback

        lines = traceback.format_exception(*record.exc_info)
        text = "".join(lines).rstrip()
        # 末端缩进对齐，避免多行在 UI 里粘连
        return "  " + text.replace("\n", "\n  ")


# 需要一并捕获的第三方 logger（uvicorn 用它们输出请求日志）
CAPTURED_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "app", "xinbot")


def install(level: int = logging.INFO) -> None:
    """安装日志缓冲。重复调用是安全的。

    **只挂根 logger**：命名 logger 会把记录向上传播给根，
    因此挂一次就能捕获全部（含 `uvicorn.*`、`app.*`）。
    曾经同时挂在根与命名 logger 上，导致同一条日志被记录两次。
    """
    root = logging.getLogger()
    if not any(isinstance(handler, BufferHandler) for handler in root.handlers):
        handler = BufferHandler()
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)

    if root.level > level or root.level == logging.NOTSET:
        root.setLevel(level)

    # uvicorn 自带的 logger 默认不向根传播，需要显式放开，
    # 否则 HTTP 请求日志不会进入缓冲（这正是"Web 上看不到访问日志"的原因）。
    for name in CAPTURED_LOGGERS:
        logger = logging.getLogger(name)
        logger.propagate = True
        if logger.level == logging.NOTSET or logger.level > level:
            logger.setLevel(level)

    _state.installed = True


def mark_server_started() -> None:
    """记录后端启动时刻（供状态接口显示运行时长）。"""
    _state.server_started_at = time.time()
    logging.getLogger("xinbot").info("XinBot Web 后端已启动")


def entries(limit: int = 100, min_level: str | None = None) -> list[dict]:
    """取最近 limit 条日志，可按级别过滤。"""
    with _state.lock:
        items = list(_state.buffer)
    if min_level:
        threshold = logging.getLevelName(min_level.upper())
        if isinstance(threshold, int):
            items = [item for item in items if logging.getLevelName(item.level) >= threshold]
    items = items[-limit:]
    return [
        {**asdict(item), "stamp": item.stamp}
        for item in items
    ]


def status() -> dict:
    """运行状态摘要（CLI 与 Web 共用同一结构）。"""
    with _state.lock:
        size = len(_state.buffer)
        counters = dict(_state.counters)
    started_at = _state.server_started_at
    return {
        "capacity": DEFAULT_CAPACITY,
        "buffered": size,
        "warnings": counters["warnings"],
        "errors": counters["errors"],
        "started_at": started_at,
        "uptime_seconds": round(time.time() - started_at, 1) if started_at else 0.0,
    }


def reset() -> None:
    """清空缓冲（测试与"清空日志"操作使用）。"""
    with _state.lock:
        _state.buffer.clear()
        _state.counters.update({"warnings": 0, "errors": 0})
