from types import SimpleNamespace

import pytest

from app.core.persona import Persona
from app.core.tools.builtin.rag import SearchKnowledgeTool
from app.rag.vector_store import VectorStore
from app.web.story import preview_story
from fastapi.testclient import TestClient


def test_persona_fields_and_knowledge_scope():
    persona = Persona(name="alice", display_name="Alice", aliases=["A"], history="Met Bob", knowledge_tags=["story"])
    assert persona.to_dict()["knowledge_tags"] == ["story"]
    assert "Met Bob" in persona.to_prompt_text()
    seen = []
    kb = SimpleNamespace(search=lambda query, k, tags: seen.append(tags) or [])
    SearchKnowledgeTool(kb, persona).execute("hello")
    assert seen == [["story"]]
    SearchKnowledgeTool(kb, Persona(name="none", display_name="None")).execute("hello")
    assert seen[-1] == []


def test_vector_search_filters_at_database_level():
    store = object.__new__(VectorStore)
    seen = []
    store._collection = SimpleNamespace(
        count=lambda: 4,
        query=lambda **kwargs: seen.append(kwargs) or {"documents": [[]], "metadatas": [[]], "distances": [[]]},
    )
    assert store.search("hello", tags=[]) == []
    assert not seen
    store.search("hello", tags=["story"])
    assert seen[0]["where"] == {"tag": {"$in": ["story"]}}


def test_story_preview_is_review_only(monkeypatch):
    class FakeClient:
        def chat(self, messages):
            assert "故事：" in messages[-1]["content"]
            return SimpleNamespace(content='{"characters":[{"name":"Alice","aliases":["A"],"personality":"kind","history":"travels","evidence":"chapter one"}]}')
    monkeypatch.setattr("app.web.story.LLMClient", FakeClient)
    candidates = preview_story("Alice travels", "Alice")
    assert candidates[0]["display_name"] == "Alice"
    assert candidates[0]["evidence"] == "chapter one"
    with pytest.raises(ValueError):
        preview_story("x" * 120001)


def test_v011_api_contract(tmp_path, monkeypatch):
    import app.core.persona as persona_module
    import app.web.routes.rag as rag_module
    import app.web.routes.persona as persona_route
    from app.core.persona import PersonaStore
    from app.web.server import app

    monkeypatch.setattr(persona_module, "PERSONAS_PATH", tmp_path / "personas.json")
    monkeypatch.setattr(PersonaStore, "_instance", None)
    monkeypatch.setattr(persona_route, "preview_story", lambda text, hints: [{"display_name": "Alice", "aliases": []}])
    class FakeKnowledge:
        def list_sources(self):
            return [{"source": "book.txt", "tag": "story", "chunks": 2}]
        def set_source_tag(self, source, tag):
            return 2 if source == "book.txt" and tag == "new" else 0
        def search(self, query, tags=None):
            return [{"tag": tags[0]}] if tags else []
    monkeypatch.setattr(rag_module, "knowledge", FakeKnowledge)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        created = client.post("/api/persona", json={"display_name": "Alice", "aliases": ["A"], "history": "Trip", "knowledge_tags": ["story"]})
        assert created.status_code == 200
        assert created.json()["data"]["knowledge_tags"] == ["story"]
        assert client.get("/api/rag/graph").json()["data"]["personas"][-1]["tags"] == ["story"]
        assert client.post("/api/rag/search", json={"query": "trip", "tags": ["story"]}).json()["data"] == [{"tag": "story"}]
        assert client.put("/api/rag/sources/book.txt/tag", json={"tag": "new"}).json()["data"]["updated"] == 2
        preview = client.post("/api/persona/story/preview", files={"file": ("book.txt", b"Alice travels")}, data={"hints": "Alice"})
        assert preview.json()["data"][0]["display_name"] == "Alice"
    monkeypatch.setattr(PersonaStore, "_instance", None)
