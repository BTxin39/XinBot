import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


def test_release_privacy_and_clean_boot(tmp_path):
    archive_path = Path(__file__).resolve().parents[1] / "dist/XinBot-v0.1.0.zip"
    if not archive_path.exists():
        pytest.skip("Build the release ZIP first")
    with zipfile.ZipFile(archive_path) as archive:
        prefix = "XinBot-v0.1.0/"
        manifest = json.loads(archive.read(prefix + "MANIFEST.json"))
        for name, digest in manifest.items():
            parts = Path(name).parts
            assert not set(parts) & {".env", "data", "pet", "node_modules", "vendor", "models"}
            assert not name.endswith((".log", ".db", ".sqlite"))
            assert hashlib.sha256(archive.read(prefix + name)).hexdigest() == digest
        assert "app/core/defaults.json" in manifest
        assert "app/web/static/dist/index.html" in manifest
        archive.extractall(tmp_path)
    root = tmp_path / "XinBot-v0.1.0"
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from app.core.persona import PersonaStore
from app.web.server import app, mount_static
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
