"""`xinbot locale` 的契约测试。

CLI 通过 `_root()` 取仓库根，测试把它指到临时目录，
否则会写真实 `data/locale.json`（数据护栏会直接判失败）。
"""

import json

import pytest
from typer.testing import CliRunner

from app.interfaces.cli import locale as locale_cli
from app.interfaces.cli.app import app
from app.services import i18n_service


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.setattr(locale_cli, "_root", lambda: tmp_path)
    return CliRunner(), tmp_path


def test_status_shows_current(cli):
    runner, _tmp = cli
    result = runner.invoke(app, ["locale"])
    assert result.exit_code == 0
    assert i18n_service.DEFAULT_LOCALE in result.output
    assert "可选" in result.output


def test_set_english_persists(cli):
    runner, tmp_path = cli
    result = runner.invoke(app, ["locale", "set", "en"])
    assert result.exit_code == 0
    assert "en" in result.output
    saved = json.loads((tmp_path / "data" / "locale.json").read_text(encoding="utf-8"))
    assert saved["locale"] == "en"


def test_regional_code_normalized(cli):
    runner, tmp_path = cli
    result = runner.invoke(app, ["locale", "set", "en-US"])
    assert result.exit_code == 0
    saved = json.loads((tmp_path / "data" / "locale.json").read_text(encoding="utf-8"))
    assert saved["locale"] == "en"


def test_unknown_locale_warns_about_fallback(cli):
    """`locale fr` 必须提示"已回落"，而不是静默成功。

    第一版用 `normalize(value) == saved` 判断，两者都会把 fr 变成 zh-CN，
    永远相等 → 回落完全静默（实测踩到）。
    """
    runner, tmp_path = cli
    result = runner.invoke(app, ["locale", "set", "fr"])
    assert result.exit_code == 0
    assert "回落" in result.output
    saved = json.loads((tmp_path / "data" / "locale.json").read_text(encoding="utf-8"))
    assert saved["locale"] == i18n_service.DEFAULT_LOCALE


def test_bare_command_shows_status(cli):
    """不带子命令时显示状态（简写 `locale en` 已移除，见模块注释）。"""
    runner, tmp_path = cli
    i18n_service.save(tmp_path, "en")
    result = runner.invoke(app, ["locale"])
    assert result.exit_code == 0
    assert "en" in result.output


def test_status_subcommand(cli):
    runner, tmp_path = cli
    i18n_service.save(tmp_path, "en")
    result = runner.invoke(app, ["locale", "status"])
    assert result.exit_code == 0
    assert "en" in result.output
