"""Live2D / 桌宠外观导入的契约测试。

真实世界里的「Live2D 模型」至少有四种形态（见 `app/services/live2d_service.py`）：
Cubism 3/4/5（新）、Cubism 2.1（旧）、夹带网页资源的工程包、多模型合集。
本文件用**构造出来的最小压缩包**覆盖这些形态，不依赖联网或大体积素材。

同时用 `scratch/` 下的真实下载包做一次回归（存在才跑）：那三个包分别是
Cubism 3、Cubism 2.1、以及带 css/js/images 的 Live2DViewerEX 工程包。
"""

import io
import json
import zipfile
from pathlib import Path

import pytest

from app.services import live2d_service as L

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"


# ── 构造工具 ──────────────────────────────────────────────────────


def make_zip(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def cubism3_files(prefix="", texture="textures/tex.png"):
    base = f"{prefix}/" if prefix else ""
    return {
        f"{base}model.model3.json": json.dumps({
            "Version": 3,
            "FileReferences": {
                "Moc": "model.moc3",
                "Textures": [texture],
                "Physics": "model.physics3.json",
                "Motions": {"": [{"File": "motions/idle.motion3.json"}]},
            },
        }),
        f"{base}model.moc3": b"moc3-bytes",
        f"{base}{texture}": b"\x89PNG fake",
        f"{base}model.physics3.json": "{}",
        f"{base}motions/idle.motion3.json": "{}",
    }


def cubism2_files(prefix="", texture="tex/t00.png"):
    base = f"{prefix}/" if prefix else ""
    return {
        f"{base}model.model.json": json.dumps({
            "version": "Sample 1.0.0",
            "model": "moc/model.moc",
            "textures": [texture],
            "motions": {"idle": [{"file": "mtn/i.mtn"}]},
            "physics": "physics.json",
        }),
        f"{base}moc/model.moc": b"moc-bytes",
        f"{base}{texture}": b"\x89PNG fake",
        f"{base}physics.json": "{}",
        f"{base}mtn/i.mtn": b"mtn",
    }


def cubism3_named(name: str, prefix="") -> dict:
    """构造一个**模型名可控**的 Cubism 3 包（测试多模型场景必需）。"""
    base = f"{prefix}/" if prefix else ""
    return {
        f"{base}{name}.model3.json": json.dumps({
            "Version": 3,
            "FileReferences": {"Moc": f"{name}.moc3", "Textures": ["textures/tex.png"]},
        }),
        f"{base}{name}.moc3": b"moc3-bytes",
        f"{base}textures/tex.png": b"\x89PNG fake",
    }


def cubism2_named(name: str, prefix="") -> dict:
    base = f"{prefix}/" if prefix else ""
    return {
        f"{base}{name}.model.json": json.dumps({
            "version": "Sample 1.0.0",
            "model": f"{name}.moc",
            "textures": ["tex/t00.png"],
        }),
        f"{base}{name}.moc": b"moc-bytes",
        f"{base}tex/t00.png": b"\x89PNG fake",
    }


# ── 识别与校验 ────────────────────────────────────────────────────


def _stage(content: bytes, tmp_path: Path):
    archive = L.open_archive(content)
    L.extract(archive, tmp_path)
    archive.close()
    return L.scan_candidates(tmp_path)


def test_detects_cubism3(tmp_path):
    candidates = _stage(make_zip(cubism3_files()), tmp_path)
    assert [c.kind for c in candidates] == ["cubism3"]
    package = L.validate(L.choose(candidates))
    assert package.name == "model"
    assert package.kind == "cubism3"


def test_detects_cubism2(tmp_path):
    candidates = _stage(make_zip(cubism2_files()), tmp_path)
    assert [c.kind for c in candidates] == ["cubism2"]
    package = L.validate(L.choose(candidates))
    assert package.name == "model"
    # 旧格式必须提示缺运行时，而不是让用户以为导入失败
    assert any("live2d.min.js" in warning for warning in package.warnings)


def test_detects_nested_layout(tmp_path):
    """深层嵌套（如 a/b/c/model/）必须能找到模型。"""
    candidates = _stage(make_zip(cubism3_files(prefix="a/b/c/model")), tmp_path)
    assert len(candidates) == 1
    assert L.validate(L.choose(candidates)).kind == "cubism3"


def test_web_bundle_is_accepted_then_pruned(tmp_path):
    """夹带 css/js/images 的工程包不能再被整体拒绝。"""
    files = cubism2_files(prefix="model/x")
    files.update({
        "css/live2d.css": "body{}",
        "js/live2d.js": "console.log(1)",
        "images/btn.png": b"img",
    })
    candidates = _stage(make_zip(files), tmp_path)
    package = L.validate(L.choose(candidates))
    L.prune_web_assets(package.root)
    remaining = {item.name for item in package.root.iterdir()}
    assert "css" not in remaining and "js" not in remaining and "images" not in remaining
    # 模型自身文件必须保留（.moc 在 moc/ 子目录里）
    assert "moc" in remaining
    assert (package.root / "moc" / "model.moc").is_file()


def test_missing_texture_is_rejected(tmp_path):
    files = cubism3_files()
    files.pop("textures/tex.png")
    candidates = _stage(make_zip(files), tmp_path)
    with pytest.raises(L.ModelImportError):
        L.validate(L.choose(candidates))


@pytest.mark.parametrize("texture", ["../escape.png", "/abs.png"])
def test_unsafe_texture_reference_is_rejected(tmp_path, texture):
    """清单里的越界/绝对路径引用必须拒绝。

    注意：这类包通常还会带一个合法纹理，否则解压阶段就会因
    路径穿越先失败——那样测的就不是"清单校验"这一层了。
    """
    files = cubism3_files()
    files["model.model3.json"] = json.dumps({
        "Version": 3,
        "FileReferences": {"Moc": "model.moc3", "Textures": [texture]},
    })
    candidates = _stage(make_zip(files), tmp_path)
    with pytest.raises(L.ModelImportError):
        L.validate(L.choose(candidates))


def test_missing_moc_is_rejected(tmp_path):
    files = cubism3_files()
    files.pop("model.moc3")
    candidates = _stage(make_zip(files), tmp_path)
    with pytest.raises(L.ModelImportError) as excinfo:
        L.validate(L.choose(candidates))
    assert ".moc3" in str(excinfo.value)


def test_missing_optional_physics_only_warns(tmp_path):
    files = cubism3_files()
    files["model.model3.json"] = json.dumps({
        "Version": 3,
        "FileReferences": {"Moc": "model.moc3", "Textures": ["textures/tex.png"],
                            "Physics": "nope.physics3.json"},
    })
    files.pop("model.physics3.json")
    candidates = _stage(make_zip(files), tmp_path)
    package = L.validate(L.choose(candidates))
    assert package.kind == "cubism3"
    assert any("Physics" in warning for warning in package.warnings)


def test_choose_prefers_cubism3(tmp_path):
    files = {}
    files.update(cubism3_files(prefix="newer"))
    files.update(cubism2_files(prefix="older"))
    candidates = _stage(make_zip(files), tmp_path)
    assert len(candidates) == 2
    assert L.choose(candidates).kind == "cubism3"


def test_choose_rejects_ambiguous_same_format(tmp_path):
    files = {}
    files.update(cubism3_files(prefix="a"))
    files.update(cubism3_files(prefix="b"))
    candidates = _stage(make_zip(files), tmp_path)
    with pytest.raises(L.ModelImportError) as excinfo:
        L.choose(candidates)
    assert "无法自动选择" in str(excinfo.value)


def test_empty_archive_is_rejected(tmp_path):
    candidates = _stage(make_zip({"readme.txt": "no model here"}), tmp_path)
    with pytest.raises(L.ModelImportError) as excinfo:
        L.choose(candidates)
    assert "没有找到可识别的模型" in str(excinfo.value)


def test_path_traversal_is_rejected():
    content = make_zip({"../outside.json": "{}"})
    archive = L.open_archive(content)
    with pytest.raises(L.ModelImportError):
        L.extract(archive, Path("."))
    archive.close()


def test_unsupported_extension_is_rejected(tmp_path):
    files = cubism3_files()
    files["payload.exe"] = b"MZ"
    archive = L.open_archive(make_zip(files))
    with pytest.raises(L.ModelImportError) as excinfo:
        L.extract(archive, tmp_path)
    archive.close()
    assert ".exe" in str(excinfo.value)


def test_not_a_zip_is_rejected():
    with pytest.raises(L.ModelImportError):
        L.open_archive(b"this is not a zip")


def test_oversized_archive_is_rejected():
    with pytest.raises(L.ModelImportError):
        L.open_archive(b"x" * (L.MAX_ARCHIVE_BYTES + 1))


# ── 运行时状态 ────────────────────────────────────────────────────


def test_runtime_state_reports_all_formats():
    state = L.runtime_state()
    for kind in ("cubism3", "cubism4", "cubism2", "sprite"):
        assert kind in state
        assert "ready" in state[kind]
    # 精灵图不需要额外运行时
    assert state["sprite"]["ready"] is True


def test_cubism2_runtime_is_optional(monkeypatch, tmp_path):
    """缺 Cubism 2.1 运行时只影响该格式，不应报错。"""
    monkeypatch.setattr(L, "vendor_root", lambda: tmp_path)
    state = L.runtime_state()
    assert state["cubism2"]["ready"] is False
    assert "live2d.min.js" in state["cubism2"]["missing_hint"]


def test_require_runtime_raises_with_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(L, "vendor_root", lambda: tmp_path)
    with pytest.raises(L.ModelImportError) as excinfo:
        L.require_runtime("cubism2")
    assert "live2d.min.js" in str(excinfo.value)


# ── 真实下载包回归 ────────────────────────────────────────────────


@pytest.mark.skipif(not SCRATCH.is_dir() or not list(SCRATCH.glob("*.zip")),
                    reason="scratch/ 下没有真实模型包")
def test_real_archives_still_import(monkeypatch, tmp_path):
    """用用户实际下载的三个包做回归。

    它们分别是 Cubism 3、Cubism 2.1、以及带网页资源的工程包——
    覆盖了当初导入失败的全部三种情形。
    """
    monkeypatch.setattr(L, "UPLOAD_ROOT", tmp_path / "imported")
    monkeypatch.setattr(L, "vendor_root", lambda: tmp_path / "vendor")
    (tmp_path / "vendor").mkdir()
    # 让两个运行时都视为就绪，专注验证"格式能否被识别并导入"
    (tmp_path / "vendor" / "live2dcubismcore.min.js").write_text("x")
    (tmp_path / "vendor" / "live2d.min.js").write_text("x")

    seen = {}
    for archive_path in sorted(SCRATCH.glob("*.zip")):
        result = L.import_from_path(archive_path)
        seen[result["kind"]] = result["name"]
        destination = tmp_path / "imported" / result["relative"]
        assert destination.is_file(), f"{archive_path.name} 的清单未落到预期位置"

    assert "cubism3" in seen, "真实包里应当至少有一个 Cubism 3 模型"
    assert "cubism2" in seen, "真实包里应当至少有一个 Cubism 2.1 模型"
