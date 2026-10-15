"""data/ 目录指纹与差异比较 —— 供 `tests/conftest.py` 与测试共用。

单独成模块的原因：`conftest.py` 不是可导入的顶层模块名（pytest 以 rootdir
插入方式加载它），测试文件无法直接 `import conftest`，因此把纯逻辑放在这里。
"""

import hashlib
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

# 这些文件本来就会被测试或运行中的服务触碰，且不属于用户数据
IGNORED_SUFFIXES = {".log"}
IGNORED_NAMES = {"web_process.json"}

LABELS = {"created": "新增", "removed": "删除", "modified": "修改"}

# 会话开始时的基线快照。
#
# 必须放在本模块（而非 conftest.py）里：`tests/conftest.py` 会被加载成
# **两个不同的模块对象**（pytest 用于注册 hook 的那个，与测试文件
# `from tests import conftest` 拿到的那个不是同一个），因此 conftest 里的
# 模块级变量在测试进程里读不到，护栏会静默失效。P3 期间实测确认过这一点。
_baseline: dict[str, str] | None = None


def capture_baseline() -> dict[str, str]:
    """记录会话开始时的 data/ 指纹。"""
    global _baseline
    _baseline = fingerprint()
    return _baseline


def baseline() -> dict[str, str] | None:
    return _baseline


def changes_since_baseline() -> dict[str, list[str]]:
    """返回相对会话基线的改动；未捕获基线时返回空。"""
    if _baseline is None:
        return {"created": [], "removed": [], "modified": []}
    return diff(_baseline, fingerprint())



def fingerprint(root: Path = DATA) -> dict[str, str]:
    """对目录内所有文件取 sha256 指纹（排序保证稳定）。"""
    if not root.is_dir():
        return {}
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in IGNORED_SUFFIXES or path.name in IGNORED_NAMES:
            continue
        try:
            snapshot[str(path.relative_to(root)).replace("\\", "/")] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        except OSError:
            continue
    return snapshot


def diff(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    """比较两次指纹，返回新增/删除/修改的清单。"""
    return {
        "created": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "modified": sorted(
            name for name in set(after) & set(before) if after[name] != before[name]
        ),
    }


def describe(changes: dict[str, list[str]]) -> str:
    """把差异渲染为人类可读的多行说明。"""
    return "\n".join(
        f"  {LABELS[key]}: {', '.join(changes[key])}" for key in LABELS if changes[key]
    )


# ── 预检：捕获"跨会话已存在"的污染 ─────────────────────────────────
#
# 指纹比对只能发现**本次会话期间**的改动。P5 收尾时发现了一个它抓不到的实例：
# `data/runtime_config.json` 里的 `db_path` 被写成了
# `C:\\Users\\...\\AppData\\Local\\Temp\\tmpXXXX\\m.db` —— 这是测试用 `tmp_path`
# 构造 `RuntimeConfig(db_path=...)` 后调用 `save()` 的结果，发生在更早的某次
# 会话里（文件时间戳显示与被污染时刻相差一个月）。
#
# 因此额外做一轮**内容预检**：这些文件里出现测试临时目录特征即视为已污染。
# 预检在会话开始时运行，指向具体文件与成因，便于立刻修复而不是继续累积。

TEMP_MARKERS = ("\\AppData\\Local\\Temp\\", "/tmp/", "\\Temp\\pytest-", "/pytest-of-")

# 需要预检的 JSON 文件：它们的默认值都指向真实的 data/ 路径，
# 一旦被测试的 tmp_path 覆盖就会静默指向临时目录。
PRECHECK_FILES = ("runtime_config.json", "llm_registry.json")


def precheck(root: Path = DATA) -> list[str]:
    """返回"已存在的污染"清单（空表示干净）。

    只做保守判断：文件内容中出现测试临时目录特征。
    """
    problems = []
    for name in PRECHECK_FILES:
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for marker in TEMP_MARKERS:
            if marker in text:
                problems.append(
                    f"data/{name} 含有测试临时路径特征 {marker!r}，"
                    "说明它被测试的 tmp_path 覆盖过"
                )
                break
    return problems

