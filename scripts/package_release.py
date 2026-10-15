"""Build a source release with prebuilt frontend and no local user data."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.0"

# 不纳入发布包的内容：依赖、字节码、测试产物、前端源码目录（只发构建产物）
EXCLUDED_PARTS = {
    "node_modules",
    "__pycache__",
    "test-results",
    "static",
    "src",
    "public",
    "tests",
}


def release_files(root: Path):
    for directory in ("app", "docs", "tests"):
        for path in sorted((root / directory).rglob("*")):
            relative = path.relative_to(root)
            if any(part in EXCLUDED_PARTS for part in relative.parts):
                continue
            if path.is_file() and not path.is_symlink() and path.suffix in {".py", ".md"}:
                yield relative
    for name in ("pyproject.toml", "uv.lock", "README.md", "app/core/defaults.json",
                 "app/interfaces/web/package.json", "app/interfaces/web/package-lock.json",
                 "scripts/download_live2d.py",
                 "scripts/package_release.py", "start.ps1", ".gitignore"):
        yield Path(name)
    for path in sorted((root / "app/interfaces/web/static/dist").rglob("*")):
        if path.is_file() and not path.is_symlink() and path.suffix in {".html", ".js", ".css"}:
            yield path.relative_to(root)


def main():
    if not (ROOT / "app/interfaces/web/static/dist/index.html").is_file():
        raise SystemExit("Run npm run build in app/interfaces/web first")
    files = sorted(set(release_files(ROOT)))
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    target = output / f"XinBot-v{VERSION}.zip"
    hashes = {}
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            content = (ROOT / relative).read_bytes()
            archive.writestr(f"XinBot-v{VERSION}/{relative.as_posix()}", content)
            hashes[relative.as_posix()] = hashlib.sha256(content).hexdigest()
        archive.writestr(f"XinBot-v{VERSION}/MANIFEST.json", json.dumps(hashes, indent=2))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".sha256").write_text(f"{digest}  {target.name}\n", encoding="ascii")
    print(f"{target}\n{len(files)} files\nSHA256: {digest}")


if __name__ == "__main__":
    main()
