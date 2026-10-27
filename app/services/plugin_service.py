"""插件系统：让用户自己扩展工具，而不必改源码。

## 为什么插件只做「工具插件」

项目里已经有 MCP 支持（外部进程 + JSON-RPC）。再做一个"什么都替换"的插件
框架会与它重叠，而且 UI 插件需要动前端架构。所以这里只解决一个明确需求：
**往 Agent 的工具箱里加自定义工具**，格式极简、行为可预期。

## 磁盘格式

```
data/plugins/
  my-plugin/
    plugin.json     # {"name","version","description","entry","enabled"}
    plugin.py       # 暴露 tools() -> list[BaseTool]
```

`plugin.py` 里必须有 `tools()` 函数，返回 `BaseTool` 实例列表：

```python
from app.core.tools.base import BaseTool

class Echo(BaseTool):
    name = "echo"
    description = "原样返回文本"
    def execute(self, **kwargs):
        return str(kwargs.get("text", ""))

def tools():
    return [Echo()]
```

## 安全边界（重要）

插件是**在当前进程里执行任意 Python 代码**的。因此：

* 只从 `data/plugins/` 加载，不扫描别处；
* 默认**需要显式启用**（`plugin.json` 里 `enabled: true`），
  用户放进来的插件不会因为文件名存在就被执行；
* 加载失败只记录并跳过，绝不让一个坏插件拖垮整个 Agent；
* 工具名统一加 `plugin_` 前缀，避免与内置工具重名而覆盖它们。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFEST_NAME = "plugin.json"
DEFAULT_ENTRY = "plugin.py"
TOOL_PREFIX = "plugin_"
REQUIRED_FIELDS = ("name", "version")


@dataclass
class PluginInfo:
    """一个插件目录的静态信息。"""

    name: str
    version: str = ""
    description: str = ""
    entry: str = DEFAULT_ENTRY
    enabled: bool = False
    path: Path | None = None
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "enabled": self.enabled,
            "path": str(self.path) if self.path else "",
            "error": self.error,
        }


@dataclass
class LoadResult:
    """一次加载的结果。"""

    tools: list = field(default_factory=list)
    loaded: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (name, 原因)

    @property
    def ok(self) -> bool:
        return not self.skipped


def plugins_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data" / "plugins"


def read_plugin(directory: Path) -> PluginInfo:
    """读一个插件目录的清单。任何问题都写进 `error` 而不是抛异常。"""
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        return PluginInfo(name=directory.name, path=directory,
                          error=f"缺少 {MANIFEST_NAME}")

    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return PluginInfo(name=directory.name, path=directory,
                          error=f"{MANIFEST_NAME} 不是合法 JSON：{error}")

    if not isinstance(raw, dict):
        return PluginInfo(name=directory.name, path=directory,
                          error=f"{MANIFEST_NAME} 必须是对象")

    missing = [key for key in REQUIRED_FIELDS if not raw.get(key)]
    if missing:
        return PluginInfo(name=directory.name, path=directory,
                          error=f"缺少字段：{', '.join(missing)}")

    name = str(raw["name"]).strip()
    entry = str(raw.get("entry") or DEFAULT_ENTRY).strip()
    if "/" in entry or "\\" in entry or entry.startswith("."):
        return PluginInfo(name=name, path=directory,
                          error="entry 只能是插件目录内的文件名")

    info = PluginInfo(
        name=name,
        version=str(raw["version"]).strip(),
        description=str(raw.get("description") or "").strip(),
        entry=entry,
        # 默认关闭：文件存在不等于允许执行
        enabled=bool(raw.get("enabled", False)),
        path=directory,
    )
    if not (directory / entry).is_file():
        info.error = f"缺少入口文件 {entry}"
    return info


def discover(repo_root: Path) -> list[PluginInfo]:
    """列出所有插件目录（含未启用与有错误的），按名字排序。"""
    root = plugins_root(repo_root)
    if not root.is_dir():
        return []
    found = [read_plugin(item) for item in sorted(root.iterdir()) if item.is_dir()]
    return sorted(found, key=lambda info: info.name)


def _load_module(info: PluginInfo):
    """把 `plugin.py` 作为独立模块导入。

    用 `spec_from_file_location` 而不是 `import`：插件目录不一定在
    `sys.path` 上，也不该污染全局导入命名空间。
    """
    assert info.path is not None
    entry = info.path / info.entry
    module_name = f"xinbot_plugin_{info.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, entry)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {entry}")
    module = importlib.util.module_from_spec(spec)
    # 注册到 sys.modules：插件内部若用到 dataclass/typing 的自省需要它
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def load(repo_root: Path, tool_registry=None) -> LoadResult:
    """加载所有**已启用**的插件工具。

    传入 `tool_registry` 时把工具直接注册进去（会做重名检查）；
    不传则只返回工具实例，便于测试。
    """
    result = LoadResult()
    for info in discover(repo_root):
        if info.error:
            result.skipped.append((info.name, info.error))
            continue
        if not info.enabled:
            result.skipped.append((info.name, "未启用"))
            continue

        try:
            module = _load_module(info)
        except Exception as error:  # noqa: BLE001  插件代码什么都能抛
            result.skipped.append((info.name, f"导入失败：{error}"))
            logger.warning("插件 %s 导入失败: %s", info.name, error)
            continue

        factory = getattr(module, "tools", None)
        if not callable(factory):
            result.skipped.append((info.name, "plugin.py 里没有 tools() 函数"))
            continue

        try:
            produced = list(factory() or [])
        except Exception as error:  # noqa: BLE001
            result.skipped.append((info.name, f"tools() 执行失败：{error}"))
            continue

        if not produced:
            result.skipped.append((info.name, "tools() 没有返回任何工具"))
            continue

        accepted = 0
        for tool in produced:
            name = getattr(tool, "name", "")
            if not name:
                result.skipped.append((info.name, "工具缺少 name"))
                continue
            if not hasattr(tool, "execute"):
                result.skipped.append((info.name, f"工具 {name} 没有 execute()"))
                continue
            # 统一前缀：避免覆盖内置工具
            if not name.startswith(TOOL_PREFIX):
                try:
                    tool.name = f"{TOOL_PREFIX}{name}"
                except Exception:  # noqa: BLE001  只读属性就保持原名
                    pass
            if tool_registry is not None:
                if tool_registry.get(tool.name) is not None:
                    result.skipped.append((info.name, f"工具名冲突：{tool.name}"))
                    continue
                tool_registry.register(tool)
            result.tools.append(tool)
            accepted += 1

        if accepted:
            result.loaded.append(info.name)
            logger.info("插件 %s 已加载 %d 个工具", info.name, accepted)
        else:
            result.skipped.append((info.name, "没有可用工具"))

    return result


def set_enabled(repo_root: Path, name: str, enabled: bool) -> bool:
    """改写 `plugin.json` 里的 `enabled`。找不到插件返回 False。"""
    for info in discover(repo_root):
        if info.name != name or info.path is None:
            continue
        manifest = info.path / MANIFEST_NAME
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(raw, dict):
            return False
        raw["enabled"] = bool(enabled)
        manifest.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    return False
