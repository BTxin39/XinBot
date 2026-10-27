"""语音输出（TTS）。

引擎选择：
    **Windows SAPI**（`SAPI.SpVoice`，通过 COM 调用）是唯一"零依赖、离线、
    系统自带"的方案：
      * 不需要额外 pip 包（pywin32 已随 desktop extra 安装）；
      * 不联网，隐私上说得清；
      * 中文声音取决于系统是否装了中文语音包，缺了会自动跳过而不是报错。
    云端 TTS（edge-tts 等）音质更好，但需要联网与新增依赖，留作后端插槽。

三个必须处理好的工程问题：
    1. **不能阻塞**：`Speak` 在阻塞模式下会卡住调用线程，必须异步 + 队列；
    2. **要能打断**：新消息来了应当立刻停掉旧的，而不是排队念完；
    3. **失败要静默**：没有语音包、COM 初始化失败时不能影响聊天，
       只在状态里标记 `available=False`。
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field


@dataclass
class SpeechConfig:
    """语音偏好。数值都做了合理范围收敛，避免把声音调到听不清。"""

    enabled: bool = False
    rate: int = 0        # SAPI Rate，范围 -10~10，0 为正常语速
    volume: int = 100    # 0~100
    voice: str = ""      # 留空 = 用系统默认声音
    max_chars: int = 200  # 单条最长朗读字数，超出截断（长回复读起来很烦）

    def normalized(self) -> "SpeechConfig":
        def clamp(value, low, high, fallback):
            try:
                return max(low, min(high, int(value)))
            except (TypeError, ValueError):
                return fallback

        return SpeechConfig(
            enabled=bool(self.enabled),
            rate=clamp(self.rate, -10, 10, 0),
            volume=clamp(self.volume, 0, 100, 100),
            voice=str(self.voice or "").strip(),
            max_chars=clamp(self.max_chars, 20, 500, 200),
        )


class SpeechBackend:
    """后端接口。测试用假后端即可，不需要真的发声。"""

    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def speak(self, text: str, *, rate: int, volume: int, voice: str) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class NullBackend(SpeechBackend):
    """静音后端：非 Windows 或用户关闭时使用。"""

    name = "null"

    def available(self) -> bool:
        return False

    def speak(self, text: str, *, rate: int, volume: int, voice: str) -> None:
        return

    def stop(self) -> None:
        return


class SapiBackend(SpeechBackend):
    """Windows 自带语音（SAPI）。

    用 `SVSFlagsAsync` 让 `Speak` 立即返回，实际朗读由系统完成；
    `stop()` 通过 `Speak("", SVSFPurgeBeforeSpeak)` 清空播放队列。
    """

    name = "sapi"

    # SAPI 常量
    SVSF_ASYNC = 1
    SVSF_PURGE = 2

    def __init__(self):
        self._voice = None
        self._lock = threading.Lock()
        self._error = ""

    def _ensure(self):
        if self._voice is not None:
            return self._voice
        import win32com.client  # 随 desktop extra 安装

        voice = win32com.client.Dispatch("SAPI.SpVoice")
        self._voice = voice
        return voice

    def available(self) -> bool:
        try:
            self._ensure()
            return True
        except Exception as error:  # noqa: BLE001  没有 SAPI / 无 pywin32
            self._error = str(error)
            return False

    def speak(self, text: str, *, rate: int, volume: int, voice: str) -> None:
        with self._lock:
            engine = self._ensure()
            engine.Rate = int(rate)
            engine.Volume = int(volume)
            if voice:
                self._select_voice(engine, voice)
            engine.Speak(text, self.SVSF_ASYNC)

    def stop(self) -> None:
        with self._lock:
            if self._voice is None:
                return
            try:
                self._voice.Speak("", self.SVSF_ASYNC | self.SVSF_PURGE)
            except Exception:  # noqa: BLE001
                pass

    def _select_voice(self, engine, wanted: str) -> None:
        """按名字或描述片段挑声音；找不到就保持默认（不要抛错）。"""
        try:
            voices = engine.GetVoices()
            for index in range(voices.Count):
                token = voices.Item(index)
                description = token.GetDescription()
                if wanted.lower() in description.lower():
                    engine.Voice = token
                    return
        except Exception:  # noqa: BLE001
            pass


def default_backend() -> SpeechBackend:
    """按平台挑默认后端；导入失败时退回静音，绝不让调用方处理异常。"""
    try:
        import sys

        if sys.platform == "win32":
            return SapiBackend()
    except Exception:  # noqa: BLE001
        pass
    return NullBackend()


@dataclass
class SpeechService:
    """带队列与打断的语音服务。

    工作线程只做一件事：从队列取文本 → 交给后端朗读。
    队列长度有上限，满了就丢最旧的（语音是"陪衬"，不该因为落后而越念越久）。
    """

    config: SpeechConfig = field(default_factory=SpeechConfig)
    backend: SpeechBackend = field(default_factory=default_backend)
    queue_size: int = 3
    _queue: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=3), repr=False)
    _worker: threading.Thread | None = field(default=None, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_text: str = field(default="", repr=False)
    _spoken_count: int = field(default=0, repr=False)

    def __post_init__(self):
        self._queue = queue.Queue(maxsize=max(1, int(self.queue_size)))
        self.config = self.config.normalized()

    # ── 对外 ──────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self.backend.available()

    def say(self, text: str, *, force: bool = False) -> bool:
        """请求朗读；返回是否真的入队。

        返回 False 的常见原因：未启用、文本为空、与上一条完全相同、
        或后端不可用。调用方**不需要**为此报错。

        `force=True` 绕过"是否启用"的判断，用于**试听**：
        试听不该改变用户的开关状态，也不该被开关拦住。
        """
        if not force and not self.config.enabled:
            return False
        cleaned = self._prepare(text)
        if not cleaned:
            return False
        with self._lock:
            # 连续相同的文本不重复念（轮询会反复送来同一条）
            if cleaned == self._last_text:
                return False
            self._last_text = cleaned
        self._ensure_worker()

        # 新内容优先：先打断正在念的，再入队
        self.backend.stop()
        try:
            self._queue.put_nowait(cleaned)
            return True
        except queue.Full:
            # 丢掉最旧的一条，避免落后于对话
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(cleaned)
                return True
            except (queue.Empty, queue.Full):
                return False

    def stop(self) -> None:
        """停止朗读并清空队列。"""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self.backend.stop()

    def shutdown(self) -> None:
        self._stop.set()
        self.stop()
        worker = self._worker
        if worker is not None:
            worker.join(timeout=1.0)
        self._worker = None

    def status(self) -> dict:
        return {
            "enabled": self.config.enabled,
            "available": self.available,
            "backend": self.backend.name,
            "rate": self.config.rate,
            "volume": self.config.volume,
            "voice": self.config.voice,
            "queued": self._queue.qsize(),
            "spoken": self._spoken_count,
        }

    def update_config(self, **changes) -> SpeechConfig:
        """更新设置；`enabled=False` 会立即停止朗读。"""
        merged = SpeechConfig(**{**self.config.__dict__, **changes}).normalized()
        self.config = merged
        if not merged.enabled:
            self.stop()
        return merged

    # ── 内部 ──────────────────────────────────────────────────

    def _prepare(self, text: str) -> str:
        """清洗待朗读文本。

        去掉 markdown 记号（`**`、`#`、代码块标记）——念出来只会变成噪音。
        """
        raw = (text or "").strip()
        if not raw:
            return ""
        cleaned = raw.replace("```", " ").replace("**", "").replace("`", "")
        cleaned = " ".join(cleaned.split())
        if len(cleaned) > self.config.max_chars:
            cleaned = cleaned[: self.config.max_chars].rstrip() + "…"
        return cleaned

    def _ensure_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run, name="xinbot-tts", daemon=True)
        self._worker.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                text = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if not text:
                continue
            try:
                self.backend.speak(
                    text,
                    rate=self.config.rate,
                    volume=self.config.volume,
                    voice=self.config.voice,
                )
                self._spoken_count += 1
            except Exception:  # noqa: BLE001  读不出来就算了，不能影响聊天
                continue


# 进程级单例：网页后端与 CLI 共用同一套语音状态
_service: SpeechService | None = None


def settings_path(root) -> "Path":
    """语音偏好文件（与桌宠窗口状态并列放在 data/ 下）。"""
    from pathlib import Path

    return Path(root) / "data" / "speech.json"


def load_config(root) -> SpeechConfig:
    """读取偏好；文件缺失或损坏都回落默认（默认关闭，避免突然出声吓到人）。"""
    import json

    path = settings_path(root)
    if not path.is_file():
        return SpeechConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SpeechConfig()
    if not isinstance(raw, dict):
        return SpeechConfig()
    known = set(SpeechConfig.__dataclass_fields__)
    return SpeechConfig(**{k: v for k, v in raw.items() if k in known}).normalized()


def save_config(root, config: SpeechConfig) -> "Path":
    import json
    from dataclasses import asdict

    path = settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(asdict(config.normalized()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def service() -> SpeechService:
    global _service
    if _service is None:
        from app.paths import repo_root

        _service = SpeechService(config=load_config(repo_root()))
    return _service


def reset_service(**kwargs) -> SpeechService:
    """重建单例（测试用）。"""
    global _service
    if _service is not None:
        _service.shutdown()
    _service = SpeechService(**kwargs)
    return _service
