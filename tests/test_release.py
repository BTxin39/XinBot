import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

VERSION = "0.2.0"

# P5：适配器层已迁至 app/interfaces，旧路径不得再出现在发布包里
LEGACY_PREFIXES = ("app/cli/", "app/web/", "app/commands/")


def test_release_privacy_and_clean_boot(tmp_path):
    archive_path = Path(__file__).resolve().parents[1] / f"dist/XinBot-v{VERSION}.zip"
    if not archive_path.exists():
        pytest.skip("Build the release ZIP first")
    with zipfile.ZipFile(archive_path) as archive:
        prefix = f"XinBot-v{VERSION}/"
        manifest = json.loads(archive.read(prefix + "MANIFEST.json"))
        for name, digest in manifest.items():
            parts = Path(name).parts
            assert not set(parts) & {".env", "data", "pet", "node_modules", "vendor", "models"}
            assert not name.endswith((".log", ".db", ".sqlite"))
            assert hashlib.sha256(archive.read(prefix + name)).hexdigest() == digest
        assert "app/core/defaults.json" in manifest
        assert "app/interfaces/web/static/dist/index.html" in manifest
        assert "app/interfaces/cli/app.py" in manifest
        assert not [
            name for name in manifest if name.startswith(LEGACY_PREFIXES)
        ], "发布包仍包含 P5 之前的旧路径"
        archive.extractall(tmp_path)
    root = tmp_path / f"XinBot-v{VERSION}"
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from app.core.persona import PersonaStore
from app.interfaces.web.server import app, mount_static
from fastapi.testclient import TestClient
assert PersonaStore.get().get_persona('xin').builtin
mount_static()
with TestClient(app, base_url='http://127.0.0.1') as client:
    assert client.get('/').status_code == 200
    assert client.get('/api/models').json()['ok']
    assert client.get('/api/memory').json()['ok']
"""
    result = subprocess.run([sys.executable, "-I", "-c", code, str(root)], cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_cli_entry_point_matches_pyproject():
    """控制台入口点必须指向真实存在的模块（P5 改了它，别让它漂移）。"""
    import tomllib

    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    script = data["project"]["scripts"]["xinbot"]
    module_path, _, attribute = script.partition(":")
    assert attribute == "app"

    candidate = root / (module_path.replace(".", "/") + ".py")
    assert candidate.is_file(), f"入口点模块不存在: {module_path} -> {candidate}"
