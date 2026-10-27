"""语音服务的契约测试。

不真的发声：注入 `RecordingBackend` 记录被朗读的文本。
重点验证三件事：
    1. 不阻塞、可打断（新消息先 stop 旧的）；
    2. 相同的重复文本不会反复念（轮询会反复送来同一条）；
    3. 后端不可用 / 未启用时 `say()` 返回 False 而不是抛异常。
"""

import threading
import time

import pytest

from app.services.speech_service import (
    NullBackend,
    SpeechConfig,
    SpeechService,
    default_backend,
)


class RecordingBackend:
    name = "recording"

    def __init__(self, available=True):
        self.spoken: list[str] = []
        self.stops = 0
        self._available = available
        self._lock = threading.Lock()
        self.done = threading.Event()

    def available(self) -> bool:
        return self._available

    def speak(self, text, *, rate, volume, voice) -> None:
        with self._lock:
            self.spoken.append(text)
        self.done.set()

    def stop(self) -> None:
        self.stops += 1

    def wait(self, timeout=2.0) -> bool:
        return self.done.wait(timeout)


def make_service(backend=None, **config) -> SpeechService:
    backend = backend or RecordingBackend()
    options = {"enabled": True}
    options.update(config)
    return SpeechService(config=SpeechConfig(**options), backend=backend, queue_size=3)


# ── 基本行为 ──────────────────────────────────────────────────────

def test_say_queues_and_speaks():
    backend = RecordingBackend()
    service = make_service(backend)
    try:
        assert service.say("你好") is True
        assert backend.wait(), "工作线程应当在后台朗读"
        assert backend.spoken == ["你好"]
    finally:
        service.shutdown()


def test_disabled_service_does_not_speak():
    backend = RecordingBackend()
    service = SpeechService(config=SpeechConfig(enabled=False), backend=backend)
    assert service.say("你好") is False
    time.sleep(0.2)
    assert backend.spoken == []


def test_unavailable_backend_reports_status():
    service = make_service(RecordingBackend(available=False))
    try:
        assert service.available is False
        assert service.status()["available"] is False
    finally:
        service.shutdown()


def test_empty_text_is_ignored():
    service = make_service()
    try:
        assert service.say("   ") is False
        assert service.say("") is False
    finally:
        service.shutdown()


# ── 去重与打断 ────────────────────────────────────────────────────

def test_identical_text_is_not_repeated():
    """轮询会反复送来同一条回复，不该一直重念。"""
    backend = RecordingBackend()
    service = make_service(backend)
    try:
        assert service.say("同一句话") is True
        assert service.say("同一句话") is False
        assert service.say("同一句话") is False
        backend.wait()
        time.sleep(0.3)
        assert backend.spoken == ["同一句话"]
    finally:
        service.shutdown()


def test_new_text_interrupts_previous():
    """来新消息时先打断旧的，而不是排队念完。"""
    backend = RecordingBackend()
    service = make_service(backend)
    try:
        service.say("第一句")
        service.say("第二句")
        assert backend.stops >= 1, "第二条之前应当先 stop"
    finally:
        service.shutdown()


def test_stop_clears_queue():
    backend = RecordingBackend()
    service = make_service(backend)
    try:
        service.say("a")
        service.stop()
        assert service.status()["queued"] == 0
        assert backend.stops >= 1
    finally:
        service.shutdown()


def test_queue_overflow_drops_oldest():
    """队列满时丢最旧的：语音只是陪衬，不该越来越落后。"""
    backend = RecordingBackend()
    service = SpeechService(
        config=SpeechConfig(enabled=True), backend=backend, queue_size=1
    )
    try:
        # 让工作线程来不及消费
        service._ensure_worker = lambda: None  # type: ignore[assignment]
        assert service.say("one") is True
        assert service.say("two") is True  # 覆盖掉 one
        assert service.status()["queued"] == 1
    finally:
        service.shutdown()


# ── 文本清洗 ──────────────────────────────────────────────────────

def test_markdown_is_stripped():
    service = make_service()
    try:
        cleaned = service._prepare("**加粗** 和 `代码` 还有\n\n换行")
        assert "**" not in cleaned
        assert "`" not in cleaned
        assert "\n" not in cleaned
    finally:
        service.shutdown()


def test_long_text_is_truncated():
    service = make_service(max_chars=20)
    try:
        cleaned = service._prepare("啊" * 200)
        assert len(cleaned) <= 21  # 20 + 省略号
        assert cleaned.endswith("…")
    finally:
        service.shutdown()


# ── 配置 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"rate": 99}, 10),
        ({"rate": -99}, -10),
        ({"volume": 999}, 100),
        ({"volume": -5}, 0),
        ({"max_chars": 1}, 20),
        ({"rate": "bad"}, 0),
    ],
)
def test_config_is_clamped(raw, expected):
    config = SpeechConfig(**raw).normalized()
    value = config.rate if "rate" in raw else config.volume if "volume" in raw else config.max_chars
    assert value == expected


def test_disable_stops_speaking():
    backend = RecordingBackend()
    service = make_service(backend)
    try:
        service.say("hello")
        service.update_config(enabled=False)
        assert service.config.enabled is False
        assert backend.stops >= 1
    finally:
        service.shutdown()


def test_status_shape():
    service = make_service()
    try:
        status = service.status()
        for key in ("enabled", "available", "backend", "rate", "volume", "queued", "spoken"):
            assert key in status
    finally:
        service.shutdown()


def test_null_backend_is_never_available():
    assert NullBackend().available() is False


def test_default_backend_is_safe_to_construct():
    """非 Windows / 缺依赖时必须退回静音后端而不是抛异常。"""
    backend = default_backend()
    assert backend.name in ("sapi", "null")
    # 能否真的发声取决于系统语音包，这里只要求查询不崩
    assert isinstance(backend.available(), bool)
