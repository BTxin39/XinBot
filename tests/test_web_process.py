import httpx
from typer.testing import CliRunner

from app.cli.app import app
from app.web import process


def test_cli_controls(monkeypatch):
    calls = []
    monkeypatch.setattr(process, 'show', lambda: calls.append('show'))
    monkeypatch.setattr(process, 'shutdown', lambda: calls.append('stop'))
    monkeypatch.setattr(process, 'launch', lambda port, dev: calls.append((port, dev)))
    runner = CliRunner()
    assert runner.invoke(app, ['start', '--show']).exit_code == 0
    assert runner.invoke(app, ['start', 'web', '--shutdown']).exit_code == 0
    assert runner.invoke(app, ['start', 'web', '--port', '3796']).exit_code == 0
    assert calls == ['show', 'stop', (3796, False)]


def test_probe_rejects_wrong_identity(monkeypatch):
    original = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'pid': 999}))
    monkeypatch.setattr(process.httpx, 'Client', lambda **kwargs: original(transport=transport, **kwargs))
    assert not process.probe({'port': 3796, 'pid': 123, 'token': 'test-only'})


def test_shutdown_does_not_touch_unknown_process(monkeypatch):
    monkeypatch.setattr(process, 'read_state', lambda: None)
    process.shutdown()
