"""分层纪律护栏（docs/DECISIONS_V0.2.md §8）。

用 AST 静态扫描强制依赖方向，防止重构成果被后续提交悄悄破坏：

    interfaces/{cli,web,commands}  →  services  →  core · config · memory · storage · rag · llm

P5 目录搬迁后，适配器层的实际位置是 `app/interfaces/`；
旧路径 `app/{cli,web,commands}` 只允许作为**兼容别名**存在，
不得重新变成真实代码目录（`test_legacy_packages_are_not_real_directories`）。

`BASELINE` 是**迁移期豁免**机制；`COMPLETED_STAGES` 里的阶段一旦标记完成，
其遗留条目会立刻让测试失败，逼迫基线保持收敛。
"""

import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

# 已完成的阶段：这些阶段的基线条目必须已清空
COMPLETED_STAGES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3", "P4"})

# 适配器层的模块前缀。规则里用它们表达"不得依赖 UI/编排层"。
ADAPTERS = ("app.interfaces",)

# 旧路径的模块前缀。P5 之后这些**不得**再被任何代码 import，
# 也不得作为目录存在（已彻底搬迁，不留兼容层）。
LEGACY_MODULES = ("app.cli", "app.web", "app.commands")

# 旧路径的目录名，用于断言它们已被删除
LEGACY_PACKAGES = ("cli", "web", "commands")


@dataclass(frozen=True)
class Rule:
    """一条依赖规则：`root` 下的模块不得 import `prefixes` 中的任何模块。"""

    root: str
    prefixes: tuple[str, ...]
    note: str


RULES: tuple[Rule, ...] = (
    Rule("core", ADAPTERS + ("app.services",), "R1：领域核心不得反向依赖 UI/编排层"),
    Rule("services", ("fastapi", "rich", "typer"), "R2：service 层不得依赖 Web 框架或终端渲染库"),
    Rule("services", ADAPTERS, "R2b：service 层不得依赖适配器层"),
    Rule("config", ADAPTERS, "R4：配置层不得依赖适配器层"),
    Rule("memory", ADAPTERS, "R4b：记忆层不得依赖适配器层"),
    Rule("storage", ADAPTERS, "R4c：存储层不得依赖适配器层"),
    Rule("rag", ADAPTERS, "R4d：RAG 层不得依赖适配器层"),
    Rule("llm", ADAPTERS, "R4e：LLM 层不得依赖适配器层"),
    Rule("events", ADAPTERS, "R4f：事件层不得依赖适配器层"),
    Rule("interfaces/commands", ("rich",), "R5：命令层不得依赖终端渲染库"),
    Rule(
        "core",
        ("rich",),
        "R6：core 是 services 的依赖，不得引入终端渲染库（否则 Web 复用被迫连带加载）",
    ),
    Rule("events", ("rich",), "R6b：events 由 core 订阅，同样不得引入渲染库"),
    Rule("config", ("rich",), "R6c：config 被 core/services 依赖，同样不得引入渲染库"),
    Rule(
        "interfaces",
        LEGACY_MODULES,
        "R7：适配器不得 import 旧路径（P5 已彻底搬迁，旧路径不存在）",
    ),
)

# R3：routes 层只允许经 services 访问具体实现
R3_PREFIXES = ("app.storage", "app.core.persona", "app.llm.registry", "app.memory")

# 迁移期豁免：{相对 app/ 的 POSIX 路径: {(被违规导入的模块前缀, 计划清理阶段)}}
BASELINE: dict[str, set[tuple[str, str]]] = {
    # R3 已全部清零（P4 完成）。保留本字典是为了让豁免机制在将来需要时可用。
}


def _module_name(path: Path) -> str:
    """把 app/ 下的文件路径换算为点分模块名。"""
    parts = list(path.resolve().relative_to(APP).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return "app." + ".".join(parts)


def _is_module(dotted: str) -> bool:
    """判断点分名是否是一个可导入的模块或包。

    用于区分 `from pkg import Name` 的两种含义（子模块 vs 模块内属性），
    否则 `PersonaStore` 会被误报成 `app.core.persona.PersonaStore`。
    第三方包（fastapi / rich / typer）同样需要被识别，故用 find_spec。
    """
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        return False


def _imported_modules(path: Path) -> set[str]:
    """收集一个文件中所有被导入的完整模块名（含相对导入解析）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _module_name(path)
    imports: set[str] = set()

    def add(dotted: str) -> None:
        if _is_module(dotted):
            imports.add(dotted)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # 相对导入：app.interfaces.web.routes.ascii_art + level=1 + ".foo"
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level])
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            if not module:
                continue
            add(module)
            for alias in node.names:
                add(f"{module}.{alias.name}")
    return imports


def _python_files(root: str) -> list[Path]:
    """列出 root 下的 .py 文件（绝对路径，保证 relative_to(APP) 可用）。"""
    directory = APP / root
    return sorted(directory.rglob("*.py")) if directory.is_dir() else []


def _relative(path: Path) -> str:
    """相对 app/ 的 POSIX 路径。"""
    return path.resolve().relative_to(APP).as_posix()


def _allowed(path: Path) -> set[tuple[str, str]]:
    return BASELINE.get(_relative(path), set())


def _is_allowed(path: Path, module: str) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix, _stage in _allowed(path)
    )


def _violations(rule: Rule) -> list[str]:
    found = []
    for path in _python_files(rule.root):
        for module in _imported_modules(path):
            if _is_allowed(path, module):
                continue
            for prefix in rule.prefixes:
                if module == prefix or module.startswith(prefix + "."):
                    found.append(f"app/{_relative(path)}: {module}  ({rule.note})")
    return found


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: f"{rule.root}:{rule.prefixes[0]}")
def test_no_forbidden_imports(rule):
    violations = _violations(rule)
    assert not violations, "检测到违规依赖：\n" + "\n".join(violations)


def test_routes_go_through_services_only():
    """R3：routes 不得直接 import 存储/注册表实现（基线豁免除外）。"""
    unexpected = []
    for path in _python_files("interfaces/web/routes"):
        relative = _relative(path)
        for module in _imported_modules(path):
            if _is_allowed(path, module):
                continue
            if any(module == prefix or module.startswith(prefix + ".") for prefix in R3_PREFIXES):
                unexpected.append(f"{relative}: {module}")
    assert not unexpected, (
        "routes 新增了绕过 service 层的直接依赖（R3）：\n"
        + "\n".join(unexpected)
        + "\n如确属迁移期，请把 (模块前缀, 清理阶段) 加入 BASELINE 并注明理由。"
    )


def test_baseline_entries_still_exist():
    """基线过期即失败：条目对应文件消失或已修复时，必须从基线中删除。"""
    stale = []
    for relative, entries in BASELINE.items():
        path = APP / relative
        if not path.is_file():
            if any(stage in COMPLETED_STAGES for _prefix, stage in entries):
                stale.append(f"{relative}：文件已不存在（阶段已完成，请删除条目）")
            continue
        imported = _imported_modules(path)
        for prefix, stage in sorted(entries):
            if not any(item == prefix or item.startswith(prefix + ".") for item in imported):
                stale.append(f"{relative}: {prefix} 已不再导入（{stage} 阶段疑似完成，请删除该条目）")
    assert not stale, "BASELINE 需要更新：\n" + "\n".join(stale)


def test_completed_stages_have_no_baseline_left():
    """已标记完成的阶段不得残留基线条目，避免豁免变成永久白名单。"""
    leftover = [
        f"{relative}: {prefix}（阶段 {stage}）"
        for relative, entries in BASELINE.items()
        for prefix, stage in sorted(entries)
        if stage in COMPLETED_STAGES
    ]
    assert not leftover, "已完成阶段仍有基线豁免：\n" + "\n".join(leftover)


# ── P5：搬迁结果与兼容别名 ────────────────────────────────────────


def test_adapters_live_under_interfaces():
    """适配器必须在 app/interfaces 下（P5 的搬迁结果）。"""
    for name in ("cli", "web", "commands"):
        assert (APP / "interfaces" / name).is_dir(), f"缺少 app/interfaces/{name}"
    assert (APP / "interfaces" / "__init__.py").is_file()


def test_legacy_packages_are_gone():
    """旧路径必须**彻底删除**，不保留任何兼容别名。

    P5 决策（用户明确要求"直接搬，不留历史包袱"）：旧目录
    `app/{cli,web,commands}` 已全部移除，`sys.modules` 别名也没有。
    若这里又出现目录，说明有人把代码搬回旧路径或加了垫片。
    """
    for name in LEGACY_PACKAGES:
        assert not (APP / name).exists(), (
            f"app/{name}/ 仍然存在；P5 已决定不保留旧路径兼容层，请删除它"
        )


def test_no_source_imports_legacy_paths():
    """整个 app/ 都不得再 import 旧路径。"""
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        for module in _imported_modules(path):
            if any(
                module == old or module.startswith(old + ".")
                for old in LEGACY_MODULES
            ):
                offenders.append(f"app/{_relative(path)}: {module}")
    assert not offenders, "仍有代码 import 旧路径：\n" + "\n".join(offenders)


def test_interfaces_do_not_import_legacy_paths():
    """R7 的具体化：适配器新代码不得 import 旧路径。"""
    assert not _violations(Rule("interfaces", LEGACY_MODULES, "R7"))


# ── 护栏自身的回归测试 ───────────────────────────────────────────


def test_import_scanner_resolves_modules():
    imported = _imported_modules(APP / "interfaces" / "web" / "routes" / "ascii_art.py")
    assert "app.interfaces.web.routes.ascii_art" not in imported
    assert "app.services.image_ascii" in imported
    assert "fastapi" in imported


def test_import_scanner_ignores_attribute_imports():
    """`from pkg.mod import Name` 不应把 `Name` 误判为子模块。

    用临时探针文件做纯单元验证，不依赖某个具体文件当前是否还有此类 import——
    否则每次重构都会让这条自测失效（P4 期间踩过）。
    """
    probe = APP / "core" / "_scanner_probe.py"
    probe.write_text(
        "from app.core.persona import PersonaStore\n"
        "from app.services import memory_service\n",
        encoding="utf-8",
    )
    try:
        imported = _imported_modules(probe)
        assert "app.core.persona" in imported
        assert "app.core.persona.PersonaStore" not in imported, "属性被误判为子模块"
        assert "app.services" in imported
        assert "app.services.memory_service" in imported
    finally:
        probe.unlink(missing_ok=True)


def test_rule_detects_known_violation():
    """护栏必须能抓到违规：core 依赖适配器层即应被拦下。"""
    probe = APP / "core" / "_layering_probe.py"
    probe.write_text(
        "from app.interfaces.cli.approval import cli_approval_callback\n", encoding="utf-8"
    )
    try:
        assert _violations(Rule("core", ("app.interfaces",), "probe"))
    finally:
        probe.unlink(missing_ok=True)
