"""Live2D 模型包检测与校验 —— CLI 与 Web 共用（新增能力）。

背景：Live2D 模型生态非常杂，同一套「Live2D」至少有四种实际形态：

    1. **Cubism 3/4/5**（新）：`*.model3.json` + `*.moc3` + 纹理
    2. **Cubism 2.1**（旧）：`*.model.json` + `*.moc` + `.mtn` 动作
    3. **旧式网页工程包**：上面两种之一，再夹带 `css/`、`js/`、`images/`
       等网页资源（Live2DViewerEX 导出、网页 demo 解包都很常见）
    4. **多模型合集**：一个大目录里平铺多个模型（如整站模型仓库）

原有的导入逻辑只认 `*.model3.json`，因此上面 2/3/4 全部被拒，且报错是
"未找到 .model3.json 或 pet.json"——用户完全无法判断问题出在哪。

本模块负责把这些形态**先识别、再校验、再选择**，供两个适配器共用：

    parse_archive(...)  → 解压（带安全校验）并识别所有候选模型
    validate(model)     → 按格式校验引用文件是否齐全
    ModelPackage        → 校验通过后的可导入结果

设计取舍：不自动"猜"缺文件。缺失必需文件时宁可给出精确报错
（缺哪个引用、期望在哪个路径），也不要产出一个加载必失败的模型目录。
"""

import io
import json
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# ── 格式常量 ──────────────────────────────────────────────────────

CUBISM3_SUFFIX = ".model3.json"
CUBISM2_SUFFIX = ".model.json"
SPRITE_MANIFEST = "pet.json"

SPRITE_EXTS = {".json", ".moc3", ".moc", ".mtn", ".png", ".webp", ".jpg", ".jpeg",
               ".wav", ".mp3", ".txt", ".md"}

# 网页工程包（Live2DViewerEX 导出、网页 demo 解包）常夹带这些资源。
# 它们不参与模型渲染，但**必须允许解压**，否则整个包会被误判为非法；
# 解压后由 `prune_web_assets()` 丢弃。
WEB_EXTS = {".css", ".js", ".html", ".htm", ".ico", ".svg", ".map"} | SPRITE_EXTS

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 1500

# 网页工程包里常见的、与模型渲染无关的目录，导入时丢弃以保持目录干净
WEB_ASSET_DIRS = {"css", "js", "images", "img", "fonts", "sounds", "styles"}


class ModelImportError(Exception):
    """模型导入失败。适配器负责翻译成 HTTP 状态码或终端提示。"""

    def __init__(self, message: str, code: str = "invalid", detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(message)


# ── 识别结果 ──────────────────────────────────────────────────────


@dataclass
class ModelCandidate:
    """一个被识别出的模型（尚未校验完整性）。"""

    manifest: Path
    root: Path            # 模型根目录（清单文件所在目录）
    kind: str             # "cubism3" | "cubism2" | "sprite"
    name: str


@dataclass
class ModelPackage:
    """校验通过、可用于导入的模型。"""

    kind: str
    name: str
    manifest: Path
    root: Path
    warnings: list[str] = field(default_factory=list)
    # 精灵图的图片路径（仅 sprite 有效；相对 root）
    spritesheet: str = ""


# ── 识别 ──────────────────────────────────────────────────────────

_CUBISM2_NAME = re.compile(r"\.model\.json$", re.IGNORECASE)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelImportError(
            f"清单文件无法解析：{path.name}", detail=str(error)
        ) from error


def _is_cubism2(manifest: Path) -> bool:
    if _CUBISM2_NAME.search(manifest.name):
        return True
    # 有些包把 .model.json 改名，仍可用内容特征判定
    try:
        data = _read_json(manifest)
    except ModelImportError:
        return False
    return "model" in data and "textures" in data and "FileReferences" not in data


def scan_candidates(root: Path) -> list[ModelCandidate]:
    """在解压目录中找出所有候选模型（含多模型合集）。"""
    candidates: list[ModelCandidate] = []

    for manifest in sorted(root.rglob("*" + CUBISM3_SUFFIX)):
        candidates.append(
            ModelCandidate(
                manifest=manifest,
                root=manifest.parent,
                kind="cubism3",
                name=manifest.name[: -len(CUBISM3_SUFFIX)],
            )
        )

    for manifest in sorted(root.rglob("*.json")):
        if manifest.name.endswith(CUBISM3_SUFFIX) or manifest.name == SPRITE_MANIFEST:
            continue
        if not _is_cubism2(manifest):
            continue
        candidates.append(
            ModelCandidate(
                manifest=manifest,
                root=manifest.parent,
                kind="cubism2",
                name=re.sub(r"\.model\.json$", "", manifest.name, flags=re.IGNORECASE),
            )
        )

    for manifest in sorted(root.rglob(SPRITE_MANIFEST)):
        candidates.append(
            ModelCandidate(manifest=manifest, root=manifest.parent, kind="sprite", name=manifest.parent.name)
        )

    return candidates


# ── 校验 ──────────────────────────────────────────────────────────


def _relative_safe(root: Path, reference: str) -> Path | None:
    """把清单里的引用解析成路径，越界或非法返回 None。"""
    if not reference or not isinstance(reference, str):
        return None
    cleaned = reference.replace("\\", "/").strip()
    if cleaned.startswith("/") or ".." in Path(cleaned).parts:
        return None
    resolved = (root / cleaned).resolve()
    return resolved if resolved.is_relative_to(root.resolve()) else None


def validate(candidate: ModelCandidate) -> ModelPackage:
    """按格式校验模型必需文件是否齐全。"""
    if candidate.kind == "sprite":
        return _validate_sprite(candidate)
    if candidate.kind == "cubism3":
        return _validate_cubism3(candidate)
    return _validate_cubism2(candidate)


def _missing(label: str, reference: str) -> ModelImportError:
    return ModelImportError(
        f"模型缺少{label}：{reference or '(清单未声明)'}",
        detail="压缩包内未找到清单所引用的文件；请确认包完整，或改用官方导出的完整模型包",
    )


def _validate_cubism3(candidate: ModelCandidate) -> ModelPackage:
    manifest = _read_json(candidate.manifest)
    refs = manifest.get("FileReferences") or {}
    if not refs:
        raise ModelImportError(
            f"{candidate.manifest.name} 不是有效的 Cubism 3+ 清单",
            detail="缺少 FileReferences 字段",
        )

    moc = refs.get("Moc")
    if not moc:
        raise ModelImportError(f"{candidate.manifest.name} 未声明 Moc 文件")
    moc_path = _relative_safe(candidate.root, moc)
    if moc_path is None or not moc_path.is_file():
        raise _missing("模型文件(.moc3)", moc)

    textures = refs.get("Textures") or []
    if not textures:
        raise ModelImportError(f"{candidate.manifest.name} 未声明纹理")
    for texture in textures:
        resolved = _relative_safe(candidate.root, texture)
        if resolved is None or not resolved.is_file():
            raise _missing("纹理", texture)

    warnings = []
    # 动作/表情/物理等属于可选资源：缺失只提示，不阻断（模型仍可显示）
    optional = {
        "Physics": refs.get("Physics"),
        "Pose": refs.get("Pose"),
        "DisplayInfo": refs.get("DisplayInfo"),
        "UserData": refs.get("UserData"),
    }
    for label, reference in optional.items():
        resolved = _relative_safe(candidate.root, reference) if reference else None
        if reference and (resolved is None or not resolved.is_file()):
            warnings.append(f"{label} 引用的文件缺失：{reference}")

    return ModelPackage(
        kind="cubism3",
        name=candidate.name,
        manifest=candidate.manifest,
        root=candidate.root,
        warnings=warnings,
    )


def _validate_cubism2(candidate: ModelCandidate) -> ModelPackage:
    manifest = _read_json(candidate.manifest)
    model = manifest.get("model")
    if not model:
        raise ModelImportError(
            f"{candidate.manifest.name} 未声明 model 字段",
            detail="Cubism 2.1 清单需要一个指向 .moc 文件的 model 字段",
        )
    resolved = _relative_safe(candidate.root, model)
    if resolved is None or not resolved.is_file():
        raise _missing("模型文件(.moc)", model)

    textures = manifest.get("textures") or []
    if not textures:
        raise ModelImportError(f"{candidate.manifest.name} 未声明纹理")
    for texture in textures:
        texture_path = _relative_safe(candidate.root, texture)
        if texture_path is None or not texture_path.is_file():
            raise _missing("纹理", texture)

    warnings = ["这是 Cubism 2.1（旧版）模型，需要额外的 live2d.min.js 运行时才能显示"]
    physics = manifest.get("physics")
    if physics:
        physics_path = _relative_safe(candidate.root, physics)
        if physics_path is None or not physics_path.is_file():
            warnings.append(f"物理文件缺失：{physics}")

    return ModelPackage(
        kind="cubism2",
        name=candidate.name,
        manifest=candidate.manifest,
        root=candidate.root,
        warnings=warnings,
    )


def _validate_sprite(candidate: ModelCandidate) -> ModelPackage:
    pet = _read_json(candidate.manifest)
    spritesheet = pet.get("spritesheetPath")
    if not spritesheet:
        raise ModelImportError(f"{candidate.manifest.name} 未声明 spritesheetPath")
    resolved = _relative_safe(candidate.root, spritesheet)
    if resolved is None or not resolved.is_file():
        raise _missing("精灵图", spritesheet)
    return ModelPackage(
        kind="sprite",
        name=pet.get("displayName") or candidate.name,
        manifest=candidate.manifest,
        root=candidate.root,
        spritesheet=spritesheet,
    )


# ── 选择主模型 ────────────────────────────────────────────────────


def choose(candidates: list[ModelCandidate]) -> ModelCandidate:
    """从候选里挑出要导入的那个。

    规则（可预测优先，不做语义猜测）：
        1. 有且仅有一个 → 就是它
        2. 多个时优先 Cubism 3+（新格式支持最好），其次精灵图，最后 Cubism 2.1
        3. 同格式仍多个 → 报错并列出全部候选，让用户自行裁剪压缩包
    """
    if not candidates:
        raise ModelImportError(
            "压缩包里没有找到可识别的模型",
            detail="需要 *.model3.json（Cubism 3+）、*.model.json（Cubism 2.1）或 pet.json + 精灵图",
        )
    if len(candidates) == 1:
        return candidates[0]

    priority = {"cubism3": 0, "sprite": 1, "cubism2": 2}
    ordered = sorted(candidates, key=lambda item: (priority[item.kind], str(item.manifest)))
    best_kind = ordered[0].kind
    same_kind = [item for item in ordered if item.kind == best_kind]
    if len(same_kind) > 1:
        listed = "、".join(item.manifest.relative_to(item.root.parent).as_posix() for item in same_kind[:8])
        raise ModelImportError(
            f"压缩包内含 {len(same_kind)} 个同级模型，无法自动选择",
            detail=f"请只保留一个模型后重试。候选：{listed}",
        )
    return ordered[0]


def list_candidates(candidates: list[ModelCandidate]) -> list[dict]:
    """供预览/列表展示。"""
    return [
        {"kind": item.kind, "name": item.name, "manifest": item.manifest.name}
        for item in candidates
    ]


# ── 解压 ──────────────────────────────────────────────────────────


def extract(archive: zipfile.ZipFile, target: Path) -> None:
    """安全解压：限制体积/数量/路径，只放行模型相关扩展名。"""
    members = archive.infolist()
    if len(members) > MAX_ENTRIES:
        raise ModelImportError("模型包条目过多", code="too_large")
    if sum(item.file_size for item in members) > MAX_EXTRACTED_BYTES:
        raise ModelImportError("解压后模型过大", code="too_large")

    resolved_target = target.resolve()
    for item in members:
        destination = (resolved_target / item.filename.replace("\\", "/")).resolve()
        if not destination.is_relative_to(resolved_target):
            raise ModelImportError("模型包包含无效路径（疑似路径穿越）")
        if item.is_dir():
            continue
        if destination.suffix.lower() not in WEB_EXTS:
            raise ModelImportError(f"模型包包含不支持的文件类型：{destination.suffix}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(item) as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)


def prune_web_assets(root: Path) -> None:
    """丢弃网页工程包里的 css/js/images 等无关目录，保持导入目录干净。"""
    for directory in list(root.rglob("*")):
        if directory.is_dir() and directory.name.lower() in WEB_ASSET_DIRS:
            # 只删不包含模型清单/纹理引用的整目录
            if not any(directory.rglob("*.moc*")) and not any(directory.rglob("*model*.json")):
                shutil.rmtree(directory, ignore_errors=True)


def open_archive(content: bytes) -> zipfile.ZipFile:
    if len(content) > MAX_ARCHIVE_BYTES:
        raise ModelImportError("模型压缩包不能超过 64 MB", code="too_large")
    try:
        return zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise ModelImportError("请上传 ZIP 模型包") from error


# ── 完整导入流程（CLI 与 Web 共用） ────────────────────────────────

# 导入模型存放目录。模块级变量而非硬编码，便于测试重定向。
# 由 `app.paths.repo_root()` 推导，避免再数目录层数。
def _default_upload_root() -> Path:
    from app.paths import repo_root

    return repo_root() / "pet" / "imported"


UPLOAD_ROOT: Path = _default_upload_root()

SPRITE_COLUMNS = 8
SPRITE_ROWS = 9
SPRITE_FRAME_COUNTS = [6, 8, 8, 4, 5, 8, 6, 6, 6]

# 各格式的运行时文件名。Cubism 2.1 的 `live2d.min.js` 属 Live2D 专有 SDK，
# 不能随本项目分发（`pixi-live2d-display` 是 MIT，但该 core 不是），
# 需用户自行放置；Cubism 3/4/5 的 core 有下载脚本。
RUNTIME_FILES = {
    "cubism3": "live2dcubismcore.min.js",
    "cubism2": "live2d.min.js",
    "sprite": None,
}
RUNTIME_HINTS = {
    "cubism3": "运行 scripts/download_live2d.py 获取 Cubism Core",
    "cubism2": "Cubism 2.1 需要自行放置 live2d.min.js（授权限制，不随项目分发）",
    "sprite": "",
}


def vendor_root() -> Path:
    from app.paths import repo_root

    return repo_root() / "pet" / "vendor"


def runtime_state() -> dict:
    """报告各格式的运行时是否就绪。"""
    root = vendor_root()
    state = {}
    for kind, filename in RUNTIME_FILES.items():
        ready = True if filename is None else (root / filename).is_file()
        state[kind] = {
            "ready": ready,
            "file": filename,
            "missing_hint": "" if ready else RUNTIME_HINTS[kind],
        }
    # 目录里扫描时 Cubism 3/4/5 统一记为 cubism3
    state["cubism4"] = dict(state["cubism3"])
    return state


def require_runtime(kind: str) -> None:
    info = runtime_state().get(kind)
    if info and not info["ready"]:
        raise ModelImportError(f"缺少运行时：{info['file']}", detail=info["missing_hint"])


def _check_sprite_grid(package: "ModelPackage") -> None:
    """精灵图必须是 8 列 9 行的网格（Codex 素材约定）。"""
    from PIL import Image

    sprite = package.root / package.spritesheet
    try:
        with Image.open(sprite) as picture:
            if picture.width % SPRITE_COLUMNS or picture.height % SPRITE_ROWS:
                raise ModelImportError(
                    "精灵图必须是 8 列 9 行图片",
                    detail=f"当前尺寸 {picture.width}×{picture.height}",
                )
            picture.verify()
    except ModelImportError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise ModelImportError("精灵图无法解码或尺寸非法") from error


def import_archive(archive: zipfile.ZipFile) -> dict:
    """执行一次完整导入，返回结果摘要。

    目录布局：`pet/imported/<uuid>/<模型名>/`
    —— 先按模型根目录重排，避免多模型合集/深层嵌套（如 `a/b/c/model/`）
    把整条路径原样带进来。
    """
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        extract(archive, stage)

        candidates = scan_candidates(stage)
        chosen = choose(candidates)
        package = validate(chosen)

        require_runtime(package.kind)
        if package.kind == "sprite":
            _check_sprite_grid(package)

        prune_web_assets(package.root)

        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        container = UPLOAD_ROOT / uuid.uuid4().hex
        container.mkdir()
        folder = package.name or "model"
        destination = container / folder
        shutil.copytree(package.root, destination)

        manifest = destination / package.manifest.name
        relative = f"{container.relative_to(UPLOAD_ROOT).as_posix()}/{folder}/{manifest.name}"
        return {
            "kind": package.kind,
            "name": package.name,
            "warnings": package.warnings,
            "location": destination.as_posix(),
            "relative": relative,
            "url": f"/media/pets/{relative}",
            "candidates": list_candidates(candidates),
        }


def import_from_path(path: str | Path) -> dict:
    """从本地 ZIP 文件导入（CLI 入口）。"""
    source = Path(path)
    if not source.is_file():
        raise ModelImportError(f"找不到文件：{path}", code="missing")
    content = source.read_bytes()
    archive = open_archive(content)
    with archive:
        return import_archive(archive)


def import_from_bytes(content: bytes) -> dict:
    """从内存中的 ZIP 字节导入（Web 上传入口）。"""
    archive = open_archive(content)
    with archive:
        return import_archive(archive)


def catalog(upload_root: Path | None = None) -> list[dict]:
    """列出已导入目录里的模型（供 CLI `model list`）。

    同一模型被重复导入时会存在多个目录；这里按 (kind, 模型名) 去重，
    保留**最近导入**的那一份（路径里带 uuid，排序不能代表新旧，
    因此显式比较清单文件的修改时间）。
    """
    root = upload_root or UPLOAD_ROOT
    if not root.is_dir():
        return []

    found: dict[tuple[str, str], dict] = {}

    def add(kind: str, name: str, manifest: Path) -> None:
        key = (kind, name)
        try:
            mtime = manifest.stat().st_mtime
        except OSError:
            mtime = 0.0
        current = found.get(key)
        if current is None or mtime > current["mtime"]:
            found[key] = {"kind": kind, "name": name, "manifest": manifest, "mtime": mtime}

    for manifest in sorted(root.rglob("*" + CUBISM3_SUFFIX)):
        add("cubism3", manifest.name[: -len(CUBISM3_SUFFIX)], manifest)

    for manifest in sorted(root.rglob("*" + CUBISM2_SUFFIX)):
        try:
            package = validate(ModelCandidate(
                manifest=manifest, root=manifest.parent, kind="cubism2",
                # 名字必须剥掉 .model.json 后缀，否则列表里会显示成 "xxx.model.json"
                name=manifest.name[: -len(CUBISM2_SUFFIX)],
            ))
        except ModelImportError:
            continue
        add("cubism2", package.name, manifest)

    for manifest in sorted(root.rglob(SPRITE_MANIFEST)):
        try:
            package = validate(ModelCandidate(manifest=manifest, root=manifest.parent,
                                              kind="sprite", name=manifest.parent.name))
        except ModelImportError:
            continue
        add("sprite", package.name, manifest)

    # 展示顺序：新格式在前，其次旧格式，最后精灵图（与 choose() 的优先级一致）
    priority = {"cubism3": 0, "cubism2": 1, "sprite": 2}
    return [
        {
            "kind": item["kind"],
            "name": item["name"],
            "manifest": item["manifest"],
            # 容器目录（`pet/imported/<uuid>/`），删除时整个容器一起移除
            "container": item["manifest"].parent.parent,
        }
        for item in sorted(
            found.values(), key=lambda entry: (priority.get(entry["kind"], 9), entry["name"])
        )
    ]


# ── 删除与重命名（CLI 与 Web 共用） ───────────────────────────────

def find_by_name(name: str, upload_root: Path | None = None) -> dict:
    """按模型名查找（大小写不敏感、按格式优先）。找不到抛领域异常。"""
    wanted = (name or "").strip()
    if not wanted:
        raise ModelImportError("模型名不能为空", code="invalid_name")
    rows = catalog(upload_root)
    for row in rows:
        if row["name"] == wanted:
            return row
    # 退化到大小写不敏感匹配，方便命令行输入
    for row in rows:
        if row["name"].lower() == wanted.lower():
            return row
    available = "、".join(row["name"] for row in rows) or "（无）"
    raise ModelImportError(
        f"找不到模型：{wanted}", code="missing", detail=f"当前已有：{available}"
    )


def container_is_shared(row: dict, upload_root: Path | None = None) -> bool:
    """该容器目录里是否还有**其它**模型。

    导入布局是 `pet/imported/<uuid>/<模型名>/`，正常情况下一个容器一个模型；
    但历史导入（或用户手工整理）可能把多个模型放进同一个容器。
    这种情况下只删该模型的子目录，保留容器与其它模型。
    """
    root = upload_root or UPLOAD_ROOT
    container = row["manifest"].parent.parent
    siblings = [
        item for item in catalog(root)
        if item["manifest"].parent.parent == container and item["manifest"] != row["manifest"]
    ]
    return bool(siblings)


def remove_model(name: str, upload_root: Path | None = None) -> dict:
    """删除一个已导入的模型。

    返回被删除的目录与是否顺带移除了空容器；不改动 `pet/live2d` 等内置目录。
    """
    row = find_by_name(name, upload_root)
    root = upload_root or UPLOAD_ROOT
    container = row["manifest"].parent.parent

    # 安全检查：只允许删除 imported 根之下的内容
    if not container.resolve().is_relative_to(Path(root).resolve()):
        raise ModelImportError("拒绝删除：目标不在导入目录内", code="invalid_path")

    shared = container_is_shared(row, upload_root)
    model_dir = row["manifest"].parent
    if shared:
        shutil.rmtree(model_dir, ignore_errors=False)
        removed_container = False
    else:
        shutil.rmtree(container, ignore_errors=False)
        removed_container = True

    return {
        "name": row["name"],
        "kind": row["kind"],
        "removed": model_dir.as_posix(),
        "container_removed": removed_container,
        "remaining": [item["name"] for item in catalog(upload_root)],
    }


def rename_model(name: str, new_name: str, upload_root: Path | None = None) -> dict:
    """重命名已导入的模型（改目录名 + 同步清单里的自引用）。

    只改「显示用」的名字不够：Cubism 3 的清单里 Moc/Textures 用的是相对路径，
    目录改名不会破坏它们；但**模型文件名**通常与目录同名，浏览器按清单加载，
    所以只要目录变了、清单不变即可。这里额外把清单文件名也改成新名字，
    避免"目录叫 A、清单叫 B"的混乱。
    """
    row = find_by_name(name, upload_root)
    cleaned = (new_name or "").strip()
    if not cleaned:
        raise ModelImportError("新名字不能为空", code="invalid_name")
    if any(char in cleaned for char in '\\/:*?"<>|'):
        raise ModelImportError("新名字不能包含路径分隔符或 Windows 保留字符", code="invalid_name")
    if cleaned == row["name"]:
        raise ModelImportError("新名字与原名字相同", code="invalid_name")

    root = upload_root or UPLOAD_ROOT
    for existing in catalog(upload_root):
        if existing["name"].lower() == cleaned.lower():
            raise ModelImportError(f"已存在同名模型：{cleaned}", code="conflict")

    old_dir = row["manifest"].parent
    target_dir = old_dir.with_name(cleaned)
    if target_dir.exists():
        raise ModelImportError(f"目标目录已存在：{target_dir.name}", code="conflict")

    manifest = row["manifest"]
    suffix = manifest.name[len(row["name"]):] if manifest.name.startswith(row["name"]) else ""
    old_dir.rename(target_dir)

    new_manifest = target_dir / manifest.name
    # 清单文件名与模型同名时一起改，保持目录内命名一致
    if suffix and manifest.stem.split(".")[0] == row["name"]:
        renamed = target_dir / f"{cleaned}{suffix}"
        if renamed != new_manifest:
            new_manifest.rename(renamed)
            new_manifest = renamed

    return {
        "old_name": row["name"],
        "name": cleaned,
        "kind": row["kind"],
        "location": target_dir.as_posix(),
        "manifest": new_manifest.name,
    }
