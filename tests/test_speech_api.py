"""`/api/speech` 的接口契约。

注意：路由会把偏好写进 `data/speech.json`，所以测试必须**把 repo_root 指到
临时目录**，否则会污染真实数据（套件里有 data_guard 会直接判失败）。
"""

import pytest

from app.interfaces.web.routes import speech as speech_route
from app.services import speech_service
from app.services.speech_service import SpeechConfig, SpeechService
from tests.test_speech_service import RecordingBackend
from tests.test_web_cards import client as web_client  # noqa: F401  (pytest fixture)


@pytest.fixture
def speech_env(tmp_path, monkeypatch):
    """隔离的语音环境：假后端 + 临时配置目录。"""
    backend = RecordingBackend()
    service = SpeechService(config=SpeechConfig(enabled=False), backend=backend)
    monkeypatch.setattr(speech_service, "_service", service)
    monkeypatch.setattr(speech_route, "repo_root", lambda: tmp_path)
    yield service, backend, tmp_path
    service.shutdown()


def test_status_reports_engine(web_client, speech_env):
    payload = web_client.get("/api/speech/status").json()["data"]
    assert payload["enabled"] is False
    assert payload["available"] is True
    assert payload["backend"] == "recording"


def test_enable_persists_to_disk(web_client, speech_env):
    _service, _backend, tmp_path = speech_env
    response = web_client.post("/api/speech", json={"enabled": True})
    assert response.status_code == 200
    assert response.json()["data"]["enabled"] is True
    saved = tmp_path / "data" / "speech.json"
    assert saved.is_file(), "开关状态必须落盘，否则重启就丢"
    assert '"enabled": true' in saved.read_text(encoding="utf-8")


def test_out_of_range_is_rejected_not_clamped(web_client, speech_env):
    """越界值直接 422 拒绝，比悄悄改成边界值更好——
    用户以为自己设成了 99，实际是 10，这种"静默修正"很难发现。
    """
    assert web_client.post("/api/speech", json={"rate": 50}).status_code == 422
    assert web_client.post("/api/speech", json={"volume": 500}).status_code == 422
    assert web_client.post("/api/speech", json={"volume": -5}).status_code == 422


def test_boundary_values_are_accepted(web_client, speech_env):
    payload = web_client.post("/api/speech", json={"rate": 10, "volume": 0}).json()["data"]
    assert payload["rate"] == 10
    assert payload["volume"] == 0


def test_test_endpoint_speaks_without_changing_state(web_client, speech_env):
    service, backend, _tmp = speech_env
    response = web_client.post("/api/speech/test", json={"text": "试听一句"})
    assert response.status_code == 200
    assert response.json()["data"]["queued"] is True
    assert backend.wait(), "试听应当真的入队"
    # 试听不该把开关永久打开
    assert service.config.enabled is False


def test_test_endpoint_requires_text(web_client, speech_env):
    assert web_client.post("/api/speech/test", json={"text": ""}).status_code == 422


def test_test_endpoint_reports_unavailable_engine(web_client, monkeypatch, tmp_path):
    service = SpeechService(config=SpeechConfig(enabled=True),
                            backend=RecordingBackend(available=False))
    monkeypatch.setattr(speech_service, "_service", service)
    monkeypatch.setattr(speech_route, "repo_root", lambda: tmp_path)
    try:
        payload = web_client.post("/api/speech/test", json={"text": "hi"}).json()
        assert payload["ok"] is False
        assert "语音引擎" in payload["error"]
    finally:
        service.shutdown()


def test_config_roundtrip_survives_reload(tmp_path):
    """写盘 → 重新读取，设置不能丢。"""
    from app.services import speech_service as module

    config = SpeechConfig(enabled=True, rate=3, volume=70, voice="Huihui")
    module.save_config(tmp_path, config)
    loaded = module.load_config(tmp_path)
    assert loaded.enabled is True
    assert loaded.rate == 3
    assert loaded.volume == 70
    assert loaded.voice == "Huihui"


def test_corrupt_config_falls_back_to_default(tmp_path):
    path = tmp_path / "data" / "speech.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    from app.services import speech_service as module

    config = module.load_config(tmp_path)
    assert config.enabled is False, "配置写坏时默认关闭，不要突然出声"
