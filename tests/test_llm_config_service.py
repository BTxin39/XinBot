"""LLM 配置与知识库 service 的契约测试（docs/DECISIONS_V0.2.md §5.2、P4）。

P4 收敛了两处跨端重复：
    - 服务商/模型/运行配置的编排与校验（原 CLI 与 Web 各一份）—— 含 D2
    - 知识库的标签/大小/协议校验（原 CLI 与 Web 各一份）

本文件锁住：
  1. `CONFIG_UPDATE_FIELDS` 是"能改什么"的**唯一来源**，CLI 与 Web 共用；
  2. 接口地址安全校验（http/https、本机限制、凭据与查询串禁止）；
  3. 当前模型/服务商切换的一致性；
  4. 知识库校验边界。
"""

import pytest

from app.config.runtime import RuntimeConfig
from app.core.persona import Persona, PersonaStore
from app.llm.registry import LLMRegistry, ModelConfig, ProviderConfig
from app.services.llm_config_service import (
    CONFIG_SECRET_FIELDS,
    CONFIG_UPDATE_FIELDS,
    LLMConfigError,
    LLMConfigService,
    normalize_base_url,
    validate_endpoint,
)
from app.services.rag_service import (
    MAX_UPLOAD_BYTES,
    RagService,
    RagServiceError,
    validate_tag,
    validate_upload,
    validate_url,
)


@pytest.fixture
def service(tmp_path, monkeypatch):
    """隔离配置路径、角色存储与注册表。"""
    import app.config.runtime as runtime_module
    import app.core.persona as persona_module

    monkeypatch.setattr(runtime_module, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(persona_module, "PERSONAS_PATH", tmp_path / "personas.json")
    monkeypatch.setattr(persona_module.PersonaStore, "_instance", None)
    PersonaStore.get()

    registry = LLMRegistry(tmp_path / "registry.json")
    registry.add_provider(
        ProviderConfig(name="alpha", provider_type="openai-compatible", api_key_env="ALPHA_KEY",
                       base_url="https://alpha.example/v1")
    )
    registry.add_model(ModelConfig(name="alpha-model", provider="alpha"))

    config = RuntimeConfig(db_path=str(tmp_path / "memory.db"))
    config.provider = "alpha"
    config.model_name = "alpha-model"
    config.save()
    return LLMConfigService(registry=registry, config=config)


# ── D2：字段白名单是唯一来源 ──────────────────────────────────────


def test_update_field_whitelist_excludes_secrets():
    """密钥类字段绝不在白名单内（写入路径与响应脱敏两侧都拦住）。"""
    for field in CONFIG_SECRET_FIELDS:
        assert field not in CONFIG_UPDATE_FIELDS


def test_apply_updates_rejects_field_outside_whitelist(service):
    with pytest.raises(LLMConfigError) as excinfo:
        service.apply_updates({"web_search_api_key": "leak"})
    assert "不允许修改配置项" in str(excinfo.value)


def test_apply_updates_rejects_mcp_servers(service):
    """mcp_servers 能启动任意子进程，不允许经运行配置接口写入。"""
    with pytest.raises(LLMConfigError):
        service.apply_updates({"mcp_servers": [{"command": "calc.exe"}]})


def test_apply_updates_applies_allowed_fields(service):
    service.apply_updates({"temperature": 0.3, "max_memory_messages": 12})
    reloaded = RuntimeConfig.load()
    assert reloaded.temperature == 0.3
    assert reloaded.max_memory_messages == 12


def test_apply_updates_ignores_none_values(service):
    """None 表示"未提供"，不应把字段清空。"""
    service.apply_updates({"temperature": None})
    assert RuntimeConfig.load().temperature == service.config.temperature


def test_apply_updates_validates_model_provider_pair(service):
    service.apply_updates({"provider": "alpha", "model_name": "alpha-model"})
    with pytest.raises(LLMConfigError):
        service.apply_updates({"model_name": "alpha-model", "provider": "nonexistent"})


def test_apply_updates_requires_known_persona(service):
    with pytest.raises(LLMConfigError):
        service.apply_updates({"persona_name": "nobody"})


def test_persona_change_rebinds_memory(service):
    """改角色时记忆绑定必须跟着走（与 PersonaService.activate 同一规则）。"""
    PersonaStore.get().add_persona(Persona(name="test-beta", display_name="Beta"))
    service.apply_updates({"persona_name": "test-beta"})
    assert RuntimeConfig.load().current_memory_name == "web-test-beta"


def test_public_config_hides_secrets(service):
    data = service.public_config()
    for field in CONFIG_SECRET_FIELDS:
        assert field not in data


# ── 接口地址安全校验（两端共享） ──────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?key=value",
        "https://example.com/v1#frag",
        "ftp://example.com",
    ],
)
def test_validate_endpoint_rejects_unsafe(url):
    with pytest.raises(LLMConfigError):
        validate_endpoint(url)


def test_validate_endpoint_allows_local_http_and_remote_https():
    validate_endpoint("http://127.0.0.1:11434")
    validate_endpoint("http://localhost:11434/v1")
    validate_endpoint("https://api.example.com/v1")
    with pytest.raises(LLMConfigError):
        validate_endpoint("http://remote.example", local_only=True)


def test_normalize_base_url_adds_v1_for_ollama():
    assert normalize_base_url("http://127.0.0.1:11434/", "ollama") == "http://127.0.0.1:11434/v1"
    assert normalize_base_url("https://api.example.com/v1/", "openai-compatible") == "https://api.example.com/v1"


# ── 连接准备（保存前的完整校验） ──────────────────────────────────


def test_prepare_connection_requires_key_for_remote(service):
    with pytest.raises(LLMConfigError):
        service.prepare_connection(
            name="beta", provider_type="openai-compatible",
            base_url="https://beta.example/v1", model="beta-model",
            api_key="", key_env="BETA_KEY",
        )


def test_prepare_connection_allows_local_ollama_without_key(service):
    prepared = service.prepare_connection(
        name="local", provider_type="ollama",
        base_url="http://127.0.0.1:11434", model="qwen", api_key="", key_env="LOCAL_KEY",
    )
    assert prepared["base_url"].endswith("/v1")
    assert prepared["needs_key_write"] is False


def test_prepare_connection_rejects_borrowed_key(service):
    """同一密钥环境变量被两个连接共用时必须拒绝。"""
    service.registry.add_provider(
        ProviderConfig(name="gamma", provider_type="openai-compatible", api_key_env="ALPHA_KEY",
                       base_url="https://gamma.example/v1")
    )
    with pytest.raises(LLMConfigError) as excinfo:
        service.prepare_connection(
            name="gamma", provider_type="openai-compatible",
            base_url="https://gamma.example/v1", model="gamma-model",
            api_key="sk-x", key_env="ALPHA_KEY",
        )
    assert excinfo.value.code == "conflict"


def test_prepare_connection_rejects_model_owned_by_other_provider(service):
    with pytest.raises(LLMConfigError) as excinfo:
        service.prepare_connection(
            name="beta", provider_type="openai-compatible",
            base_url="https://beta.example/v1", model="alpha-model",
            api_key="sk-x", key_env="BETA_KEY",
        )
    assert excinfo.value.code == "conflict"


def test_prepare_connection_does_not_write_anything(service):
    """准备阶段必须无副作用：否则会出现"密钥写了但连接没存"。"""
    before = service.registry.data["providers"][:]
    with pytest.raises(LLMConfigError):
        service.prepare_connection(
            name="beta", provider_type="openai-compatible",
            base_url="http://remote.example/v1", model="beta-model",
            api_key="", key_env="BETA_KEY",
        )
    assert service.registry.data["providers"] == before


def test_apply_connection_registers_provider_and_model(service):
    prepared = service.prepare_connection(
        name="beta", provider_type="openai-compatible",
        base_url="https://beta.example/v1", model="beta-model",
        api_key="sk-x", key_env="BETA_KEY",
    )
    service.apply_connection(prepared)
    assert service.registry.get_provider("beta") is not None
    assert service.registry.get_model("beta-model").provider == "beta"


# ── 当前模型 / 服务商切换 ────────────────────────────────────────


def test_set_active_model_syncs_provider(service):
    service.registry.add_provider(
        ProviderConfig(name="beta", provider_type="openai-compatible", api_key_env="BETA_KEY")
    )
    service.registry.add_model(ModelConfig(name="beta-model", provider="beta"))

    config = service.set_active_model("beta-model")
    assert config.model_name == "beta-model"
    assert config.provider == "beta"
    assert RuntimeConfig.load().model_name == "beta-model"


def test_set_active_model_unknown_raises(service):
    with pytest.raises(LLMConfigError) as excinfo:
        service.set_active_model("ghost")
    assert excinfo.value.code == "missing"


def test_set_active_provider_unknown_raises(service):
    with pytest.raises(LLMConfigError):
        service.set_active_provider("ghost")


def test_remove_active_model_refused(service):
    with pytest.raises(LLMConfigError) as excinfo:
        service.remove_model("alpha-model")
    assert excinfo.value.code == "conflict"


def test_remove_provider_with_models_refused(service):
    with pytest.raises(LLMConfigError) as excinfo:
        service.remove_provider("alpha")
    assert excinfo.value.code == "conflict"


# ── 知识库校验（两端共享） ────────────────────────────────────────


@pytest.mark.parametrize("tag", ["", "   ", "x" * 65])
def test_validate_tag_rejects(tag):
    with pytest.raises(RagServiceError):
        validate_tag(tag)


def test_validate_tag_trims():
    assert validate_tag("  story  ") == "story"


def test_validate_upload_checks_type_and_size():
    validate_upload(".txt")
    validate_upload(".pdf")
    validate_upload(".txt", MAX_UPLOAD_BYTES)
    with pytest.raises(RagServiceError):
        validate_upload(".exe")
    with pytest.raises(RagServiceError) as excinfo:
        validate_upload(".txt", MAX_UPLOAD_BYTES + 1)
    assert excinfo.value.code == "too_large"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com", "example.com"])
def test_validate_url_rejects(url):
    with pytest.raises(RagServiceError):
        validate_url(url)


def test_validate_url_accepts_http_and_https():
    assert validate_url("https://example.com") == "https://example.com"
    assert validate_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"


# ── RagService 编排 ──────────────────────────────────────────────


class FakeKnowledge:
    def __init__(self):
        self.calls = []
        self.sources = [{"source": "a.txt", "tag": "story", "chunks": 3}]

    def list_sources(self):
        return self.sources

    def search(self, query, k=5, tags=None):
        self.calls.append(("search", query, k, tags))
        return [{"source": "a.txt", "text": "hit", "score": 1.0}]

    def ingest_file(self, path, tag="default"):
        self.calls.append(("ingest_file", str(path), tag))
        return {"status": "ok", "file": str(path), "chunks": 1}

    def ingest_url(self, url, tag="default"):
        self.calls.append(("ingest_url", url, tag))
        return {"status": "ok", "chunks": 1}

    def remove_source(self, source):
        return 3

    def set_source_tag(self, source, tag):
        self.calls.append(("set_source_tag", source, tag))
        return 2 if source == "a.txt" else 0

    def clear(self):
        self.calls.append(("clear",))


def test_rag_service_normalizes_tag_before_ingest(tmp_path):
    fake = FakeKnowledge()
    service = RagService(knowledge=fake)
    service.ingest_path(tmp_path / "doc.txt", tag="  story  ")
    assert fake.calls[-1] == ("ingest_file", str(tmp_path / "doc.txt"), "story")


def test_rag_service_rejects_bad_tag_before_touching_store(tmp_path):
    fake = FakeKnowledge()
    service = RagService(knowledge=fake)
    with pytest.raises(RagServiceError):
        service.ingest_path(tmp_path / "doc.txt", tag="")
    assert fake.calls == []


def test_rag_service_missing_source_tag_raises():
    with pytest.raises(RagServiceError) as excinfo:
        RagService(knowledge=FakeKnowledge()).set_source_tag("missing.txt", "x")
    assert excinfo.value.code == "missing"


def test_rag_service_url_ingest_failure_becomes_domain_error():
    class Failing(FakeKnowledge):
        def ingest_url(self, url, tag="default"):
            return {"status": "error: unreachable"}

    with pytest.raises(RagServiceError) as excinfo:
        RagService(knowledge=Failing()).ingest_url("https://example.com")
    assert excinfo.value.code == "upstream"


def test_rag_service_rejects_bad_url_before_touching_store():
    fake = FakeKnowledge()
    with pytest.raises(RagServiceError):
        RagService(knowledge=fake).ingest_url("file:///etc/passwd")
    assert fake.calls == []
