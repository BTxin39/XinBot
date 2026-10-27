"""主题服务的契约测试。

两条关键性质：
    1. **未知主题回落默认**，不能让主题名写错就白屏；
    2. **默认主题的变量值必须等于改造前的最终色值** —— 这组测试是
       "零视觉回归"的守门人：改坏了这里，默认外观就会变。
"""

import json

import pytest

from app.services import theme_service
from app.services.theme_service import DEFAULT_THEME, THEMES, list_themes, resolve, validate


def test_default_theme_exists():
    assert DEFAULT_THEME in THEMES


def test_list_themes_shape():
    items = list_themes()
    assert len(items) >= 4
    for item in items:
        assert {"name", "label", "description", "variables"} <= set(item)
        assert item["variables"], f"{item['name']} 没有变量"


def test_all_themes_define_the_same_variable_set():
    """少一个变量，那处界面就会掉回默认绿——必须齐全。"""
    keys = [set(theme.variables) for theme in THEMES.values()]
    first = keys[0]
    for index, other in enumerate(keys[1:], start=2):
        assert other == first, f"第 {index} 套主题的变量集合不一致"


def test_required_variables_present():
    required = {
        "--xin-bg", "--xin-surface", "--xin-surface-2", "--xin-border",
        "--xin-text", "--xin-text-muted", "--xin-accent",
        "--xin-accent-strong", "--xin-accent-soft",
    }
    for theme in THEMES.values():
        missing = required - set(theme.variables)
        assert not missing, f"{theme.name} 缺少变量 {missing}"


def test_colors_are_hex():
    for theme in THEMES.values():
        for key, value in theme.variables.items():
            assert value.startswith("#") and len(value) == 7, f"{theme.name}.{key}={value}"


def test_default_theme_matches_pre_theme_styles():
    """默认主题必须是"改造前"的色值，否则会改变现有外观。

    这些值来自 style.css / workspace.css 里的实际硬编码色。
    """
    spring = THEMES[DEFAULT_THEME].variables
    assert spring["--xin-bg"] == "#f8faf9"        # body 背景
    assert spring["--xin-surface"] == "#ffffff"    # 卡片/顶栏
    assert spring["--xin-surface-2"] == "#edf4ef"  # .new-workspace .companion 最终值
    assert spring["--xin-accent"] == "#376f55"     # 品牌绿
    assert spring["--xin-accent-strong"] == "#2a5c44"
    assert spring["--xin-accent-soft"] == "#eaf2ed"
    assert spring["--xin-text"] == "#273730"


def test_resolve_unknown_falls_back():
    assert resolve("nope").name == DEFAULT_THEME
    assert resolve("").name == DEFAULT_THEME
    assert resolve(None).name == DEFAULT_THEME


def test_resolve_is_case_insensitive():
    assert resolve("OCEAN").name == "ocean"
    assert resolve("  Amber  ").name == "amber"


def test_validate_reports_available_names():
    problem = validate("nope")
    assert problem and "spring" in problem
    assert validate("ocean") is None


# ── 持久化 ────────────────────────────────────────────────────────

def test_load_defaults_when_missing(tmp_path):
    assert theme_service.load(tmp_path) == DEFAULT_THEME


def test_save_and_load_roundtrip(tmp_path):
    saved = theme_service.save(tmp_path, "grape")
    assert saved == "grape"
    assert theme_service.load(tmp_path) == "grape"
    payload = json.loads((tmp_path / "data" / "theme.json").read_text(encoding="utf-8"))
    assert payload["name"] == "grape"


def test_save_normalizes_unknown(tmp_path):
    """写进未知名字时落盘的是默认值，而不是把脏数据留在文件里。"""
    assert theme_service.save(tmp_path, "does-not-exist") == DEFAULT_THEME
    assert theme_service.load(tmp_path) == DEFAULT_THEME


def test_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "data" / "theme.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    assert theme_service.load(tmp_path) == DEFAULT_THEME


def test_save_is_atomic(tmp_path):
    theme_service.save(tmp_path, "ocean")
    assert list((tmp_path / "data").glob("*.tmp")) == []


# ── 接口 ──────────────────────────────────────────────────────────

@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.interfaces.web.routes import themes as themes_route
    from app.interfaces.web.server import app

    monkeypatch.setattr(themes_route, "repo_root", lambda: tmp_path)
    return TestClient(app, base_url="http://127.0.0.1")


def test_api_lists_themes(api):
    data = api.get("/api/themes").json()["data"]
    assert [item["name"] for item in data["items"]]
    assert data["current"] == DEFAULT_THEME
    assert data["default"] == DEFAULT_THEME


def test_api_switches_and_persists(api, tmp_path):
    response = api.post("/api/theme", json={"name": "ocean"}).json()
    assert response["ok"] is True
    assert response["data"]["current"] == "ocean"
    assert response["data"]["variables"]["--xin-accent"] == "#2c5f86"
    assert theme_service.load(tmp_path) == "ocean"


def test_api_rejects_unknown_theme(api):
    payload = api.post("/api/theme", json={"name": "nope"}).json()
    assert payload["ok"] is False
    assert "spring" in payload["error"]


def test_api_rejects_empty_name(api):
    assert api.post("/api/theme", json={"name": ""}).status_code == 422


def test_api_current_endpoint(api):
    api.post("/api/theme", json={"name": "amber"})
    assert api.get("/api/theme").json()["data"]["current"] == "amber"
