# XinBot 分层重构技术决策书（CLI / Web 双端）

> 版本: v0.2 | 日期: 2026-09-21 | 状态: ✅ 全部阶段完成（P0–P6）
>
> 本文档是 `docs/DECISIONS_V0.1.md` 与 `docs/DECISIONS_V0.1.1.md` 的续篇，只处理**架构分层**问题，
> 不改变已生效的产品范围与功能边界（功能边界以 V0.1 / V0.1.1 / `docs/WEB_COMPANION.md` 为准）。
>
> 结论先行：**CLI 保留，且是长期能力，不降级为 Web 客户端。**
> 要清理的是 `app/commands/handler.py` 这一层历史包袱，以及 Web routes 里直接承载的业务逻辑。

---

## 1. 决策方向总览

| # | 决策 | 类型 |
| --- | ------ | ------ |
| 1.1 | CLI 与 Web 是**并列适配器**，不得互相实现对方职责 | 架构定位 |
| 1.2 | 新增 `app/services/`，承载跨端业务编排 | 新增分层 |
| 1.3 | 目录重组为 `app/core · app/services · app/interfaces/{cli,web,commands}` | 目录变更 |
| 1.4 | 依赖方向单向：`interfaces → services → core`，禁止反向 | 强制纪律 |
| 1.5 | 依赖注入：`Agent` 不再内建 CLI 审批回调 | 关键修复 |
| 1.6 | 命令层去 rich 化，`/slash` 命令三端共用 | 关键修复 |
| 1.7 | Agent 生命周期统一由 `AgentRuntime` 管理 | 关键修复 |
| 1.8 | 跨端语义一致性：角色-记忆绑定、审批语义、配置校验单一来源 | 关键修复 |
| 1.9 | 删除 `core/session.py` 中的"假共用" API | 清理 |

---

## 2. 现状诊断

### 2.1 功能重复面（已核实）

同一组业务能力，在 core 之上被实现了两遍（CLI 一遍、Web routes 一遍）：

| 能力 | CLI 侧 | Web 侧 | 重复度 |
| ------ | -------- | -------- | -------- |
| 配置 / 服务商 / 模型 | `app/cli/config.py` (295 行) | `app/web/routes/models.py` (275 行) + `app/web/routes/config.py` | 高 |
| 角色管理 | `app/cli/persona.py` (203 行) | `app/web/routes/persona.py` (132 行) | 中高 |
| 记忆管理 | `app/cli/memory.py` (247 行) | `app/web/routes/memory.py` (177 行) | 高 |
| 知识库 | `app/cli/rag.py` (144 行) | `app/web/routes/rag.py` (89 行) | 中 |
| 状态查询 | `app/cli/status.py` (21 行) | `app/web/routes/status.py` (19 行) | 中 |

前端 `app/web/src/views/` 中的 `MemoryView`、`PersonaView`、`SettingsView`、`KnowledgeView`、`TerminalView`
即 CLI 子命令的图形化复刻，印证了"一个能力三处实现（core / CLI / Web）"的现状。

### 2.2 语义漂移清单（比行数冗余更严重）

这些不是风格问题，是**同一操作两端结果不同**的活缺陷：

| # | 现象 | 位置 | 影响 |
|---|------|------|------|
| D1 | CLI 切换角色只改 `persona_name`；Web 额外写 `current_memory_name = f"web-{name}"` | `app/cli/persona.py` vs `app/web/routes/persona.py` | ✅ **P3 已修复**：两端统一调用 `PersonaService.activate()`，命名收敛为 `memory_name_for_persona()` |
| D2 | 配置更新用手写 `setattr` 循环，**字段白名单实际由 pydantic schema 提供**（`ConfigUpdateRequest` 已设 `extra="forbid"`，`mcp_servers` 写入实测返回 422）；但"允许改哪些字段"这一策略只存在于 Web schema，CLI 无对应约束，两端校验规则不共享 | `app/web/routes/config.py` + `app/web/schemas.py` | ✅ **P4 已修复**：白名单收敛为 `llm_config_service.CONFIG_UPDATE_FIELDS`，两端共用；密钥类字段两侧设界 |
| D3 | CLI 侧 `ToolGuard(cli_approval_callback)`；Web 侧 `ToolGuard()`（无回调）。而 `guard.py` 自身文档声明"无回调时默认拒绝" | `app/core/agent.py` vs `app/web/agent_manager.py` | ✅ **P0 已修复**：改为构造参数注入，`approval_mode` 显式暴露 |
| D4 | CLI 经 `ChatMemory`（含内存缓存 + 构造时跑 `migrate_from_json()`）读写；Web 直接开 `SQLiteStore` 写库 | `app/memory/chat_memory.py` vs `app/web/routes/memory.py` | ✅ **P3 已修复**：统一经 `MemoryService`；并补上 CLI 常驻进程的 `sync_if_stale()` 缓存失效机制 |
| D5 | Agent 初始化 + 灌入 `first_mes` 问候语逻辑写了两遍 | 原 `app/core/session.py` vs `app/web/agent_manager.py` | ✅ **P1 已修复**：收敛为 `AgentRuntime._inject_greeting()`，两个旧模块已删除 |

### 2.3 依赖方向倒置（✅ P0/P1 已全部修复）

| 违规边 | 原位置 | 处置 |
|--------|--------|------|
| `core → cli` | `app/core/agent.py` 导入 `cli_approval_callback` | ✅ P0：改为构造参数注入，回调实现迁至 `app/cli/approval.py` |
| `config → cli` | `app/config/cli_ui_settings.py` 导入 `app/cli/ascii_pets` | ✅ P0：模块迁至 `app/cli/ui_settings.py`（CLI 私有） |
| `web → cli` | `app/web/routes/ascii_art.py` 导入 `app/cli/image_to_ascii` | ✅ P0：迁至 `app/services/image_ascii.py`（两端共用） |
| `core → commands` | `app/core/session.py` 导入 `app.commands.handler` | ✅ P1：`SessionRunner` 迁至 `app/services/session.py`，命令分派器改为**协议注入** |

P1 处置的额外收益：`app/services/session.py` 现在只依赖 `CommandDispatcher` 协议，
命令层的具体实现由 `app/cli/session.py` 注入——所以 P2 给命令层去 rich 化时，
**不需要再动 service 或 core 一行代码**。

`BASELINE` 中的 `core/session.py` 条目已随文件删除而移除，
`COMPLETED_STAGES` 已加入 `P1`（残留豁免会让护栏失败）。

### 2.4 死代码与半成品

| 对象 | 现状 |
|------|------|
| ~~`app/core/session.py`~~ | ✅ P1 已删除（迁为 `app/services/session.py`，去掉假共用 API） |
| ~~`app/web/agent_manager.py`~~ | ✅ P1 已删除（由 `app/services/agent_runtime.py` 取代） |
| `app/commands/handler.py` | 位于通用包名下，实际 198 行全部 `rich.console.print` / `rich.Table`，Web 无法复用（P2） |
| `app/web/routes/memory.py` `/api/memory/terminal` | 手搓文本命令解析器，与 `app/commands/handler.py` 职责重叠（各写一套）（P2） |
| `app/cli/chat.py` | 已退化为仅保留导入兼容性的空壳（P6） |
| `app/cli/start.py` | 含 `fastapi`、`live_2d` 两个 `deprecated=True` 子命令（P6） |


---

## 3. 决策 1：CLI 与 Web 并列，CLI 不降级

### 3.1 选中方案

```.frame
        ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────┐
        │ interfaces/cli   │  │ interfaces/web   │  │ interfaces/commands│
        │ typer + rich     │  │ FastAPI routes   │  │ /slash 解析 → 事件  │
        │ DesktopPetUI     │  │ REST + WebSocket │  │ 无 rich 依赖        │
        └────────┬─────────┘  └────────┬─────────┘  └─────────┬──────────┘
                 └───────────┬─────────┴──────────────────────┘
                    ┌────────▼─────────┐
                    │  app/services/   │   ← 当前缺失的一层
                    │  persona · memory│
                    │  rag · llm_config│
                    │  agent_runtime   │
                    └────────┬─────────┘
                    ┌────────▼─────────┐
                    │ core/config/memory│
                    │ rag/llm/events    │
                    └──────────────────┘
```

### 3.2 保留 CLI 的理由（写入约束，防止后续被"优化"掉）

1. **冷启动能力**：服务没起来时 `xinbot doctor` / `config` / `rag ingest` / `persona` 必须可用。
2. **后端启动器与守护者**：`app/web/process.py` 的控制令牌机制依赖 CLI 侧发起与校验
   （`xinbot start web` / `--shutdown` / `--show`）。
3. **无 GUI 环境**：SSH、无桌面会话、CI 场景下 CLI 是唯一入口。
4. **可脚本化**：终端环境下可作为管道的一环，Web 不具备此性质。

**反向约束**：禁止把 CLI 改成"必须先启动 Web 才能用"的 HTTP 客户端。

### 3.3 明确不做

- 不引入前后端共享 schema 自动生成（本地单机项目，收益低于成本）。
- 不引入消息队列 / 事件总线中间件（沿用 HTTP + WebSocket）。
- 不引入用户系统与多会话（沿用 V0.1 §1.3 与 §8 的假设）。

---

## 4. 决策 2：目录重组

目标结构（迁移映射）：

```.tree
app/
├── core/                     # 领域与服务，零 UI 依赖  [保留]
│   ├── agent.py              #   改：构造注入 approval_callback
│   ├── state.py  schemas.py  persona.py
│   ├── session.py            #   改：删除 SessionUI / chat_once
│   └── tools/                #   [保留]
│
├── services/                 # 新增：跨端业务编排（无 fastapi / 无 rich）
│   ├── agent_runtime.py      #   Agent 单例 + 重建 + 首次问候
│   ├── persona_service.py
│   ├── memory_service.py
│   ├── rag_service.py
│   ├── llm_config_service.py
│   └── image_ascii.py        #   ✅ P0 已迁入（原 app/cli/image_to_ascii.py）
│
├── interfaces/               # 新增：适配器层
│   ├── cli/                  #   自 app/cli/* 迁入
│   │   ├── app.py  start.py  debug.py
│   │   ├── config.py  status.py  version.py  memory.py
│   │   ├── prompt.py  persona.py  rag.py  doctor.py
│   │   ├── desktop_ui.py  ascii_pets.py  chat.py(空壳)
│   │   ├── ui_settings.py    #   ✅ P0 已迁（原 app/config/cli_ui_settings.py；P5 随本目录移动）
│   │   └── approval.py       #   ✅ P0 已建（cli_approval_callback 的归属地）
│   ├── commands/             #   自 app/commands/handler.py 迁入并去 rich 化
│   └── web/                  #   自 app/web/* 迁入（routes 变薄壳）
│
├── config/  memory/  storage/  rag/  llm/  events/    #  [保留]
```

### 4.1 迁移影响面（✅ P5 已完成）

> 实际搬迁结果见 §10 的「P5 执行记录」。下面保留决策时的预估，便于对照。

| 项 | 影响 |
| ---- | ------ |
| `tests/test_web_process.py` | `from app.cli.app import app` 需同步改为新路径 |
| `tests/test_release.py` | 校验 `app/core/defaults.json`、`app/web/static/dist/index.html` 相对路径，需保持一致 |
| `scripts/package_release.py` | 递归收集 `app/`，无需维护清单；但需确认 `static/dist` 与 `defaults.json` 路径未变 |
| `pyproject.toml` | `[project.scripts] xinbot`、`[tool.setuptools.package-data]` 指向需更新 |
| `app/web/vite.config.js` | `outDir: static/dist` 与静态挂载路径需同步 |
| 前端 | `app/web/src/*` 通过 `/api` `/ws` 通信，路径不变则无影响 |

### 4.2 迁移策略

**决策：新目录与旧包并存一个阶段，用转发 `__init__` 保持导入兼容，全部测试通过后再删旧包。**
不做一次性大搬迁——当前无分层测试护栏，一次性搬迁无法判断回归来源。

---

## 5. 决策 3：`app/services/` 抽取规则

### 5.1 服务层契约

1. 不 `import fastapi`、不 `import rich`、不 `import typer`。
2. 不抛 `HTTPException`、不调 `console.print`；只抛领域异常（建议统一 `ServiceError(code, message)`）。
3. 输入是纯数据结构（dataclass / pydantic 均可用，但不含 HTTP 语义）。
4. 返回纯数据；**副作用（保存、重建 Agent、清缓存）在服务层内部完成，不交给路由**。
5. `HTTPException` / 退出码只在适配器层翻译。

### 5.2 逐项迁移映射

| 服务 | 吸收自 | 关键裁决 |
| ------ | -------- | ---------- |
| `llm_config_service` | `cli/config.py` 的 provider/model 命令 + `web/routes/models.py` + `web/routes/config.py` | 以 Web 版的安全校验为准（endpoint 校验、密钥不共用、per-connection env）；CLI 命令改为薄壳复用同一 service |
| `persona_service` | `cli/persona.py` + `web/routes/persona.py` + `web/character_cards.py` | **必须统一 D1**：切换角色的记忆策略只能有一份定义 |
| `memory_service` | `cli/memory.py` + `web/routes/memory.py` | **必须统一 D4**：只保留"服务层经 `MemoryManager`"一条读写路径，路由不再直连 `SQLiteStore` |
| `rag_service` | `cli/rag.py` + `web/routes/rag.py` | 校验（大小、类型、标签长度）下沉到 service |
| `agent_runtime` | `web/agent_manager.py` + `core/session.py` 的 `init()` | 见 §7 |
| `ui_settings` / `image_ascii` | `config/cli_ui_settings.py`、`cli/image_to_ascii.py` | ✅ **P0 已完成**：`image_ascii` → `app/services/`；`ui_settings` → `app/cli/`（CLI 私有，非 service——它只服务终端宠物） |

### 5.3 D1 / D4 的裁决口径（✅ P3 已实施）

- **D1（角色切换 → 记忆）**：**统一为"每个角色绑定独立记忆"，命名沿用 `web-{name}`。**
  即 Web 的既有行为成为两端共同行为，CLI 的 `persona set` 已改为调用同一
  `PersonaService.activate()`。

  **关于命名前缀的最终裁决（Q1 关闭）**：**保留 `web-` 前缀，不做改名迁移。**
  理由：
  1. 该前缀已在 `docs/WEB_COMPANION.md` 作为对外承诺写明，改名属破坏性变更；
  2. 改名需要改写用户 `data/xinbot.db` 中的记忆键，属不可逆操作；
  3. D1 的**实际危害**（两端命名分叉、CLI 切角色不切记忆）由
     `app/services/memory_service.py::memory_name_for_persona()` 收敛为唯一实现即可消除，
     与名字里有没有 `web-` 无关。

  实现位置：`app/services/memory_service.py`（命名常量 + 函数）、
  `app/services/persona_service.py::activate()`（唯一激活语义）。
  将来若确要改名，应在 `memory_name_for_persona()` 内加**读旧名兼容层**，
  而不是直接改常量。

  ⚠️ **行为变更提示（CLI）**：修复前 `xinbot persona set X` 只换角色、不换记忆，
  用户会继续在旧记忆里对话；修复后会切到 `web-X`，**表现为空的新会话**。
  这是既有设计意图（`WEB_COMPANION.md` 已如此约定），但与部分用户的历史观感不同，
  若收到反馈应优先解释而非回退。

- **D4（记忆读写路径）**：**以 `MemoryService` 为唯一路径**，
  路由直连 `SQLiteStore` 的写法已由 §8 的护栏自动拦截（`web/routes/memory.py` 条目已清零）。
  额外补上了原计划未提及的一环：**CLI 常驻进程的缓存失效机制**——
  `ChatMemory.sync_if_stale()` 在每轮对话前检测两个信号
  （磁盘上的 `current_memory_name` 变化、数据库消息条数变化），命中即重新加载，
  并清空运行摘要（其上下文已失效）。


---

## 6. 决策 4：命令层去 rich 化，三端共用

### 6.1 现状

- `app/commands/handler.py`：`/help /clear /history /status /config /remember` 及情绪命令，全部直接 rich 输出。
- `app/web/routes/memory.py` 的 `/api/memory/terminal`：独立手搓 parser（`list|show|create|use|clear|delete|describe`）。

同一个"文本命令 → 动作"概念存在两套互不相干的实现。

### 6.2 选中方案

命令层改为**"解析 → 返回结构化结果/事件"**，渲染下沉到适配器：

```python
# interfaces/commands/registry.py （示意）
@dataclass
class CommandResult:
    kind: str                      # "text" | "table" | "confirmation" | "affirm"
    payload: dict                  # 渲染所需数据，无 rich 对象
    defers_to_agent: bool = False  # True 表示应交由 LLM 处理

def dispatch(agent, user_input: str) -> CommandResult | None:
    """命中的命令返回结果；未命中返回 None（交给 LLM）。"""
```

- CLI 侧：拿到 `CommandResult` 后用 rich 渲染（现有富文本表现不降级）。
- Web 侧：`/api/memory/terminal` 改为调用同一注册表，返回 JSON，**删除手搓 parser**。
- 情绪命令、`/clear`、`/history`、`/status`、`/config`、`/remember` 全部纳入。

### 6.3 验收标准

- 新增命令只写一处，三端（终端、WebSocket 聊天、Web 终端视图）自动可用。
- `interfaces/commands/` 目录内 grep `rich` 结果为 0。

---

## 7. 决策 5：Agent 生命周期统一

### 7.1 现状（P1 前）

- CLI：`SessionRunner(agent_factory=...)` 每次启动新建 Agent，改配置要求重启进程。
- Web：`AgentManager` 单例 + 懒加载；`AgentManager.shutdown()` 在 routes 中出现 8 处
  （`config` 1 / `models` 3 / `memory` 3 / `persona` 1），另在 `server.py` 生命周期钩子 1 处。
- 两处都实现了"新建 Agent + 灌 `first_mes` 问候语"。

### 7.2 已实施方案（✅ P1 完成）

`app/services/agent_runtime.py` 是唯一生命周期入口。实际落地的 API：

```python
class AgentRuntime:
    # 类级入口（Web 等进程级共享场景）
    @classmethod
    def get(cls) -> Agent: ...          # 懒加载单例
    @classmethod
    def instance(cls) -> Agent | None: ...  # 只读查询，不触发构造
    @classmethod
    def rebuild(cls) -> None: ...       # 释放旧实例，下次 get() 重建（惰性）
    @classmethod
    def shutdown(cls) -> None: ...      # 立即释放（应用退出）
    @classmethod
    def chat(cls, message, **options) -> str: ...
    lock = RLock()                      # 与旧 AgentManager.lock 用法兼容

    # 实例入口（可注入回调，供 CLI / 测试）
    def __init__(self, approval_callback=None): ...
    def agent(self) -> Agent: ...
    def invalidate(self) -> None: ...
    def send(self, message, **options) -> str: ...
    def stream(self, message, **options): ...
    def refresh_persona(self, name: str) -> bool: ...  # 角色编辑后热更新运行实例
```

与原计划的差异（有意为之）：

| 原计划 | 实际 | 原因 |
|--------|------|------|
| `rebuild()` 返回新 Agent | 返回 `None`，**惰性重建** | 校验失败的路由不会再白白销毁运行中的 Agent；重建时机不再散落到各处 |
| `set_approval(callback)` 事后改回调 | 改为**构造时注入** | 事后改回调和 P0 修掉的 D3 是同一个反模式 |
| `shutdown()` 释放 MCP | `invalidate()`/`release()` 负责释放 | `rebuild()` 与 `shutdown()` 语义统一：都必须释放子进程 |

`refresh_persona()` 是从 `web/routes/persona.py` 搬进 service 的逻辑：
原代码直接读 `AgentManager._instance.persona` 并改 `SearchKnowledgeTool.persona`，
属于路由操作 service 内部状态，现由 service 自持。

- routes 不再直接调用 `AgentManager.shutdown()`；`app/web/routes/**` 中该引用已 **0 处**
  （`server.py` 生命周期钩子改用 `AgentRuntime.shutdown()`，属正常退出路径，保留）。
- CLI 的"重启进程生效"行为不变（Q4 仍待裁决）；底层已走同一 `AgentRuntime`/`SessionRunner`。
- Q5 保持现状：Web 端审批仍为"无回调 → fail-safe 拒绝"，只是表达方式改为构造参数。

### 7.3 涉及 D5（✅ 已消除）

`first_mes` 注入收敛为 `AgentRuntime._inject_greeting()` 一个私有方法。
`app/core/session.py` 与 `app/web/agent_manager.py` 均已删除。


---

## 8. 决策 6：依赖纪律与自动护栏

### 8.1 允许的依赖方向

```
interfaces/{cli,web,commands}  ──►  services  ──►  core · config · memory · storage · rag · llm · events
```

### 8.2 禁止项（可测试）

| 编号 | 规则 |
| ------ | ------ |
| R1 | `app/core/**` 不得 import `app/interfaces/**`（含旧 `app/cli`） |
| R2 | `app/services/**` 不得 import `fastapi`、`rich`、`typer` |
| R3 | `app/interfaces/web/routes/**` 不得 import `app/storage/sqlite_store`、`app/core/persona.PersonaStore`、`app/llm/registry.LLMRegistry` 等具体实现，只能经 services |
| R4 | `app/config/**` 不得 import `app/interfaces/**` |
| R5 | `app/interfaces/commands/**` 不得 import `rich` |
| R6 | `app/core/**`、`app/events/**`、`app/config/**` 不得 import `rich`（它们被 services 依赖，引入渲染库会让 Web 被迫连带加载） |

### 8.3 护栏实现

新增 `tests/test_layering.py`，基于 AST 静态扫描（不新增运行时依赖）：

```python
FORBIDDEN = {
    "app/core": {"app.interfaces", "app.cli"},
    "app/services": {"fastapi", "rich", "typer"},
    "app/config": {"app.interfaces", "app.cli"},
    "app/interfaces/commands": {"rich"},
    # R3 以模块级 import 黑名单表达
    "app/interfaces/web/routes": {"app.storage.sqlite_store", "app.core.persona", "app.llm.registry"},
}
```

**决策：护栏测试与 `tests/test_release.py` 同级，纳入发布前必跑清单。**

✅ **P0 已落地**：`tests/test_layering.py`（16 项）。实现要点与偏差记录：

1. `BASELINE` 为**统一豁免表**（R1/R3/R5 共用），每条标注清理阶段；
   `COMPLETED_STAGES` 中的阶段一旦标记完成，其残留条目会让测试立即失败，
   避免豁免退化成永久白名单。
2. 扫描器用 `importlib.util.find_spec` 区分 `from pkg import Name` 的两种含义，
   否则 `PersonaStore` 会被误报为子模块。**实现过程中该扫描器先后暴露 3 个自身缺陷**
   （相对路径未解析导致静默跳过全部文件、绝对导入被错误拼接当前包名、
   `import fastapi` 被属性过滤误杀），故补了 3 个护栏自测；
   另用注入真实违规的方式验证过真阳性（`app/core/zz_layering_probe.py` → 正确失败）。
3. `app/commands/handler.py` 的 rich 依赖（R5）与 `app/core/session.py` 的
   `core → commands`（R1）是**扫描发现的额外违规**，不在原设计清单内，
   已入基线分别标注 P2 / P1。

**R3 违规基线（✅ P4 已清空）**：`BASELINE = {}`，`app/web/routes/**` 全部经 services。
迁移期曾记录 5 个文件条目，P3 清 2 个（memory / persona），P4 清 3 个（config / models / rag）。

`app/web/character_cards.py` 位于 routes 之外，属 service 候选（P3 迁入 `persona_service`），未列入本表。

---

## 9. 决策 7：依赖注入取代内建 CLI 回调

### 9.1 现状

`app/core/agent.py` 构造时硬编码 `ToolGuard(cli_approval_callback)`，
Web 端只能在其后**覆盖** `_guard`（`AgentManager` 中的赋值），属于补丁式修正。

### 9.2 选中方案

```python
# core/agent.py
class Agent:
    def __init__(
        self,
        config: RuntimeConfig | None = None,
        approval_callback: ApprovalCallback | None = None,
    ):
        ...
        self.tool_manager = ToolManager(
            self.tool_registry,
            guard=ToolGuard(approval_callback),
        )
```

- CLI：`Agent(config, approval_callback=cli_approval_callback)`
- Web：`Agent(config, approval_callback=None)` → 按 `guard.py` 既有设计 fail-safe 拒绝。
- 若后续需要 Web 端审批，通过 WebSocket 下发确认事件，**不修改 core 的默认语义**。

### 9.3 涉及 D3

本决策**不改变**"Web 端危险工具默认拒绝"的既有承诺（`docs/WEB_COMPANION.md` 第 39–40 行），
只把该语义从"补丁覆盖"变成"构造参数显式表达"，并在两端状态接口中暴露当前审批模式，
使能力差异可见而非隐式。

---

## 10. 实施阶段

| 阶段 | 内容 | 验收 | 风险 | 状态 |
| ------ | ------ | ------ | ------ | ------ |
| P0 | 依赖倒置 + 护栏：`approval_callback` 注入、`ui_settings`/`image_ascii` 迁出、新增 `tests/test_layering.py` | 全部测试绿；R1/R4 无违规 | 低 | ✅ **完成**（177 passed） |
| P1 | `agent_runtime` + 生命周期收敛，消除 D5 | `AgentManager.shutdown()` 在 routes 中归零 | 中（涉 MCP 进程释放） | ✅ **完成**（188 passed） |
| P2 | `interfaces/commands/` 去 rich 化，替换 `/api/memory/terminal` 手搓 parser | 命令新增单点生效；R5 通过 | 中 | ✅ **完成（命令层部分）**（213 passed） |
| P3 | `memory_service` + `persona_service`，裁决 D1 / D4 并写回本文档 | 两端同操作结果一致；R3 通过 | **高**（触及已有用户记忆数据，需迁移方案与回滚） | ✅ **完成**（239 passed） |
| P4 | `llm_config_service` + `rag_service`，routes 变薄壳 | CLI 命令与 Web 接口共用同一校验 | 中 | ✅ **完成**（280 passed） |
| P5 | 目录搬迁至 `interfaces/`，更新 `pyproject.toml` / 测试路径 / 删旧包 | `pytest` 全绿 + `package_release.py` 可出包 | 中 | ✅ **完成**（286 passed，发布包已重建） |
| P6 | 清理死代码：命令转发层、`cli/chat.py` 空壳、`deprecated` 子命令、空目录与假警报检查 | grep 无引用 + 测试锁住"不得复活" | 低 | ✅ **完成**（287 passed） |

### P0 执行记录

| 变更 | 文件 |
|------|------|
| 新增审批回调归属地 | `app/cli/approval.py` |
| `Agent` 改为构造注入 `approval_callback`，新增 `approval_mode` 字段 | `app/core/agent.py` |
| 移除 `cli_approval_callback` 与 `_truncate`（改由 CLI 提供） | `app/core/tools/guard.py` |
| 删除事后覆盖 `_guard` 的补丁写法 | `app/web/agent_manager.py` |
| CLI 两处调用点改为注入回调 | `app/cli/start.py`、`app/cli/debug.py` |
| `image_to_ascii` → 两端共用 service | `app/services/image_ascii.py`（原 `app/cli/image_to_ascii.py` 已删） |
| `cli_ui_settings` → CLI 私有模块 | `app/cli/ui_settings.py`（原 `app/config/cli_ui_settings.py` 已删） |
| 更新引用 | `app/cli/{start,config,doctor,desktop_ui}.py`、`app/web/routes/ascii_art.py` |
| 新增测试 | `tests/test_layering.py`(16)、`tests/test_approval_injection.py`(5) |

**遗留待办**：无（README / USER_GUIDE 的旧路径已在 P0 内一并修正）。

**环境说明**：执行前该工作区被 Windows 文件权限阻断（DSH 无法为工作区根目录授予写权限，
症状为所有命令以 `SetNamedSecurityInfoW failed (Win32 5): grantWrite(...)` 失败）。
已用 `diagnose-windows-sandbox-acl` 技能修复并验证，回滚脚本位于
`D:\Users\BTxin\acl-recovery\`。

### P1 执行记录

| 变更 | 文件 |
|------|------|
| 新增 Agent 生命周期唯一入口（单例/惰性重建/释放/状态） | `app/services/agent_runtime.py` |
| `SessionRunner` 迁出领域层，命令处理改为协议注入 | `app/services/session.py` |
| 新增 CLI 侧装配层（服务层不得 import 命令层，见 R2b） | `app/cli/session.py` |
| 删除旧单例管理器 | ~~`app/web/agent_manager.py`~~（已删） |
| 删除领域层会话模块 | ~~`app/core/session.py`~~（已删） |
| 路由改用 `AgentRuntime` | `app/web/routes/{chat,config,memory,models,persona,status}.py`、`app/web/server.py` |
| `chat` 路由去掉重复的 `first_mes` 注入 | `app/web/routes/chat.py` |
| `persona` 路由的热更新逻辑移入 service | `app/services/agent_runtime.py:refresh_persona()` |
| 更新测试 | `tests/test_web_cards.py`（fixture 与 greeting/chat 用例） |
| 新增测试 | `tests/test_agent_runtime.py`(11) |

**P1 过程中发现的设计问题（已修）**：`app/commands/handler.py` 属于适配器层，
若由 `services` 直接 import 会违反 R2b。最终解法是把分派器做成协议注入，
装配点放在 `app/cli/session.py`——这不仅满足纪律，也让 P2 去 rich 化时无需改动 service/core。

**P1 契约固化**（`tests/test_agent_runtime.py`）：
`rebuild()` 必须释放旧实例（Agent 持有 MCP 子进程，丢引用即泄漏）；
重建必须惰性；`app/web/routes/**` 中 `AgentManager` 引用必须为 0；
`agent_manager.py` / `core/session.py` 不得复活。

### P2 执行记录（命令层去 rich 化）

| 变更 | 文件 |
|------|------|
| 新增结果契约（`text`/`table`/`confirmation`/`affirm`） | `app/commands/result.py` |
| 命令注册与执行改为**返回结构化结果**，零渲染依赖 | `app/commands/registry.py` |
| 新增纯文本渲染（Web / 无 rich 环境复用） | `app/commands/format.py` |
| 新增 rich 渲染（CLI 专用） | `app/cli/command_render.py` |
| `CommandHandler` 旧位置改为兼容转发 | `app/commands/handler.py` |
| 分派器协议改为返回结果；新增 `on_command_result` 钩子 | `app/services/session.py` |
| 装配点接线（rich 渲染注入） | `app/cli/session.py` |
| `DesktopPetUI` 新增 `on_command_result`，**不再清屏**（详见下） | `app/cli/desktop_ui.py` |
| 去除渲染库依赖 | `app/config/validation.py`（原导入期 `rich.console`）、`app/events/listeners.py`（原 `rich.console`） |
| 新增测试 | `tests/test_command_layer.py`(22) |
| 新增护栏规则 | `tests/test_layering.py` R6/R6b/R6c |

**执行中发现的三个真实缺陷（都不在原计划里）**：

1. **命令层"看起来"已去 rich，实际仍被迫加载。** 用 `sys.meta_path` 拦截 rich 才暴露出来：
   `app/config/validation.py` 与 `app/events/listeners.py` 都在**导入期** import rich，
   而它们分别被 `Agent` 直接 import 与订阅，于是任何走 `Agent` 的链路（含 Web）
   都被迫加载 rich。这两处才是"命令层无法脱离 rich"的真正原因。
   - `validation.py`：改为只抛 `ConfigValidationError(errors)`，打印交回适配器；
     顺带修掉一个既有问题——原实现把明细 print 到终端后只抛一句
     "Configuration validation failed"，调用方 catch 后**看不到任何原因**。
   - `listeners.py`：改用 `print()`，行为不变（每次情绪变化打印一行）。
2. **`SessionRunner.handle_command` 之后调 `ui.on_start()` 会清屏，把命令输出擦掉。**
   也就是说重构前的 `/help`、`/status` 在桌面宠物 UI 里是"闪一下就没"。
   现在 `DesktopPetUI.on_command_result` 只重绘宠物与表头，不清屏。
3. **R6 系列护栏缺口**：原规则只禁止 `commands` 层依赖 rich，
   但 `core`/`events`/`config` 这些被 services 依赖的下层同样不该引入渲染库。
   已补 R6/R6b/R6c，当前三处均无违规。

**P2 未做（有意保留）**：`/api/memory/terminal` 的手搓 parser 仍在 `app/web/routes/memory.py`。
原因：它命令集（`list|show|create|use|clear|delete|describe`）与斜杠命令集
（`/help /clear /history /status /config /remember`）**几乎不重叠**，
真正重复的是"记忆操作编排"而非"解析"——那属于 P3 的 `memory_service`。
把解析搬到命令层会同时改动前端契约（`TerminalView.vue` 与
`tests/test_web_management.py::test_memory_workflow` 都断言现有命令名与响应结构），
因此此项随 P3 一起做更合适。P2 已提供它所需的前提：命令层现在可被 Web 安全导入。

### P3 执行记录（D1 / D4 收敛）

| 变更 | 文件 |
|------|------|
| 新增记忆业务编排（列表/读取/建删/清空/激活/画像） | `app/services/memory_service.py` |
| 新增角色业务编排；**激活语义唯一实现** | `app/services/persona_service.py` |
| `ChatMemory` 新增 `sync_if_stale()`（缓存失效） | `app/memory/chat_memory.py` |
| `MemoryManager` 暴露同步能力，并在写入前自检 | `app/memory/manager.py` |
| 记忆路由改为只做协议转换（不再 import SQLiteStore） | `app/web/routes/memory.py` |
| 角色路由改为经 service（不再 import PersonaStore/Persona） | `app/web/routes/persona.py` |
| CLI `persona set` 改为调用同一 `activate()`（**D1 修复点**） | `app/cli/persona.py` |
| 新增测试 | `tests/test_memory_service.py`(17)、`tests/test_data_isolation.py`(8) |
| **修复既有测试隔离缺陷** | `tests/test_summarizer.py`（详见下） |
| 新增套件级数据护栏 | `tests/conftest.py`、`tests/data_guard.py` |

**执行中发现的既有缺陷（不在原计划里，且影响用户数据）**：

`tests/test_summarizer.py` 的 `ChatMemory` 用例没有隔离 `db_path`，
而 `RuntimeConfig` 默认指向 **`data/xinbot.db`（用户真实数据库）**。
实测确认：跑一次测试就会对真实库中的 `test_trim` 记忆执行 `clear()` 并写入。
它之所以一直没被发现，是因为测试文件本身看起来完全合理（用了"唯一的 memory_name"）。
已修（改为 `tmp_path`），并加套件级护栏：会话前后对整个 `data/` 取指纹，
期间有任何增删改就让套件**以退出码 1 失败**并打印差异清单。

护栏本身踩到一个坑并已固化：`tests/conftest.py` 会被加载成**两个不同的模块对象**
（pytest 注册 hook 用的那个，与 `from tests import conftest` 拿到的不是同一个），
因此基线快照不能放 conftest 的模块级变量，否则 `pytest_sessionfinish` 永远读到 None、
护栏静默失效。现基线放在 `tests/data_guard.py`，并有契约测试锁住。

### P4 执行记录（llm_config / rag service，D2 收敛）

| 变更 | 文件 |
|------|------|
| 新增 LLM 连接/模型/运行配置编排；**字段白名单唯一来源**（D2） | `app/services/llm_config_service.py` |
| 新增知识库编排与共享校验（标签/类型/大小/协议） | `app/services/rag_service.py` |
| 配置路由变薄壳（不再 import `LLMRegistry` / `PersonaStore`） | `app/web/routes/config.py` |
| 连接与模型路由变薄壳（不再 import `LLMRegistry` / `RuntimeConfig`） | `app/web/routes/models.py` |
| 知识库路由变薄壳（不再 import `KnowledgeBase` / `PersonaStore`） | `app/web/routes/rag.py` |
| CLI `config` 的 provider/model 增删与切换改走 service | `app/cli/config.py` |
| CLI `rag` 改走 service，并新增 `--tag`（与 Web 一致） | `app/cli/rag.py` |
| 新增测试 | `tests/test_llm_config_service.py`(41) |

**Q3 裁决（D2）**：采用**选项 A**——字段白名单搬进 service，
成为 `CONFIG_UPDATE_FIELDS`，CLI 与 Web 共用同一份"能改什么"的定义。
`web_search_api_key` 与 `mcp_servers` 明确**不在**白名单内
（前者是密钥，后者能启动任意子进程），且 `CONFIG_SECRET_FIELDS` 保证它们
也不会出现在对外响应里——写入与读取两侧都设了界。

**验收结果**：R3 基线**清空**（`BASELINE = {}`）——
`app/web/routes/**` 已不再直接 import 任何存储/注册表/领域实现，全部经 services。

**密钥处理的边界（有意保留在 Web 侧）**：`.env` 落盘
（`app/web/credentials.py` 的 `write_secret`）仍留在 Web 适配器，
因为 CLI 从不写 `.env`（其 provider 靠环境变量），不存在需要共享的重复实现。
但**"该用哪个密钥环境变量""能否复用原密钥"**的判断已进 service，
因为它们属于业务规则。`save_connection` 的顺序也被固定为
**先校验、后写密钥、最后落 registry**，避免"密钥写了但连接没存"。

**过程中修掉的一处测试脆弱性**：`test_v011.py` 原先 monkeypatch
`app.web.routes.rag.knowledge` 返回假知识库对象；P4 后路由经 `RagService`，
因此改为替换路由的 service 构造器并注入假知识库，
既保住该契约测试，又让 service 内的真实校验逻辑仍然被执行。
同时给该构造器加了注释说明"不要改成换名 import，否则 monkeypatch 会失效"。

**优先级建议**：P0 → P1 → P3 是收益最高的三段；P5（目录搬迁）**放在最后**，
它只改善可读性，不解决任何语义缺陷，却是回归风险最高的一步。

### P5 执行记录（目录搬迁）

**Q6 裁决**：用户明确要求"直接搬（不保留旧的），不要保留任何历史包袱"。
因此**未保留任何兼容别名**——旧目录 `app/{cli,web,commands}` 已彻底删除，
也没有 `sys.modules` 垫片。

| 变更 | 说明 |
|------|------|
| 新建适配器层 | `app/interfaces/{__init__,cli,web,commands}` |
| 搬迁 | `app/cli/*`、`app/web/*`、`app/commands/*` 全量移入（含前端 `static/dist`） |
| 导入改写 | 27 个文件（新包内部 + tests + scripts），行首正则改写，非逐 token |
| 入口点 | `pyproject.toml`：`xinbot = "app.interfaces.cli.app:app"` |
| 打包范围 | `package-data` / `exclude` 指向 `app.interfaces.web` |
| 版本 | `0.2.0`（`pyproject.toml` 与 `package_release.py` 同步） |
| 发布包 | 重建为 `dist/XinBot-v0.2.0.zip`（119 文件） |
| 新增测试 | 旧目录必须不存在、全仓不得 import 旧路径、入口点模块真实存在 |

**搬迁中暴露的三类"语法检查抓不到"的问题**（这也是 P5 风险的真实来源）：

1. **`Path(__file__).resolve().parents[N]` 全部算错。** 三个文件的层数各不同，
   第一轮修正后仍错了一层，实测才确认：
   `server.py` / `process.py` 应取 `parents[3]`、`routes/models.py` 应取 `parents[4]`
   （我此前按 `parents[4]`/`parents[5]` 改，结果落到了仓库根之外的上级目录）。
   **最终不再数层数**，改为 `app/paths.py::repo_root()`——向上查找含
   `pyproject.toml` / `.git` 的目录。这类写法与层级无关，未来再搬迁也不会错。

2. **字符串形式的模块名不是 import 语句。** `web/process.py` 用
   `[sys.executable, '-m', 'app.web.process', ...]` 启动子进程；
   搬迁后它会去 `app.web` 找模块并直接失败。已改为 `app.interfaces.web.process`。

3. **已安装的控制台入口点是生成物。** `.venv/Scripts/xinbot.exe` 里写死了
   `from app.cli.app import app`；改 `pyproject.toml` 并不会更新它，
   用户执行 `xinbot version` 会得到 `ModuleNotFoundError: No module named 'app.cli'`。
   已用 `uv pip install --no-deps --offline -e .` 重装（0.1.0 → 0.2.0）修复并验证。
   **发布说明里必须提示用户重装**，否则这是升级后第一个会撞到的问题。


**验收基线已达成**：`AgentManager.shutdown()` 在 `app/web/routes/**` 中由 8 处 → **0 处**；
`app/web/server.py` 1 处改为 `AgentRuntime.shutdown()`（正常退出路径，保留）。

---

## 11. 与既有决策的关系

| 既有条目 | 关系 |
| ---------- | ------ |
| V0.1 §1.1 单体多进程 | 不变 |
| V0.1 §2.3 `AgentManager` 单例 | **被本决策书 §7 取代**：改为 `AgentRuntime`，接口语义保留 |
| V0.1 §8 假设 2（不处理多用户会话，Agent 全局单例） | 不变 |
| `WEB_COMPANION.md` L39–40（Web 拒绝危险工具、非逐 token 流式） | 不变，本决策书 §9 仅改变其表达方式 |
| `WEB_COMPANION.md` L25–26（激活角色选择 `web-{id}` 记忆） | ✅ **P3 已确认为两端共同行为**，命名保持不变（见 §5.3 裁决） |
| V0.1 §2.4（删除 `app/backend/`） | 同一思路的延续：消除并行实现 |

---

## 12. 未决问题（需在对应阶段前拍板）

| # | 问题 | 阻塞阶段 | 状态 |
| --- | ------ | ---------- | ------ |
| Q1 | D1 最终记忆命名：角色维度中立名 vs 保留 `web-{name}`；是否提供自动迁移与回滚 | P3 | ✅ **已裁决**：保留 `web-{name}`，不做改名迁移（§5.3） |
| Q2 | `memory_service` 读写路径统一后，是否需要为 CLI 常驻进程增加缓存失效机制（当前 `ChatMemory.messages` 是进程内缓存） | P3 | ✅ **已实现**：`ChatMemory.sync_if_stale()`，并在 `MemoryManager.add_message` 前自检 |
| Q3 | `/api/config` 的 `setattr` 是否需要同步收窄字段白名单（D2），或仅靠 service 层约束 | P4 | ✅ **已裁决**：选项 A，白名单收敛为 `CONFIG_UPDATE_FIELDS`，两端共用 |
| Q4 | `AgentRuntime.rebuild()` 是否在 CLI 会话中暴露（如 `/reload` 命令），还是维持"重启进程生效" | P1 | 待裁决（P1 已按"维持现状"实现，不阻塞） |
| Q5 | Web 端是否需要真正的审批通道（WebSocket 确认事件），或长期维持"默认拒绝 + 状态可见" | P1 | 待裁决（P0 已按"默认拒绝"实现，不阻塞） |
| Q6 | 目录搬迁是否需要保留 `app.cli` 别名一个发布周期以兼容外部脚本 | P5 | ✅ **已裁决**：不保留任何别名，旧目录彻底删除（用户要求"不留历史包袱"）。**代价：用户升级后必须重装**（见 P5 执行记录第 3 条） |

---

## 13. 变更记录

| 版本 | 日期 | 说明 |
| ------ | ------ | ------ |
| v0.2 | 2026-09-21 | 初稿：确立 CLI/Web 并列定位、`app/services/` 分层、依赖纪律与分阶段实施计划 |
| v0.2 | 2026-09-21 | P0 完成：审批回调改注入（D3 修复）、`ui_settings`/`image_ascii` 归属修正、`test_layering.py` 护栏落地（扫描发现 R5 与 `core→commands` 两处额外违规）；修正 D2 表述（写路径白名单实由 pydantic schema 提供） |
| v0.2 | 2026-09-21 | P1 完成：新增 `AgentRuntime`（惰性重建 + 确定性释放）与 `services/session.py`（命令分派改协议注入）；删除 `web/agent_manager.py` 与 `core/session.py`；D5 消除，routes 中生命周期调用归零。执行中发现并解决了 `services` 不得 import 命令适配器（R2b）的装配位置问题 |
| v0.2 | 2026-09-21 | P2 命令层去 rich 化：新增 `commands/{result,registry,format}.py` 与 `cli/command_render.py`，命令层改为返回结构化结果。过程中用"拦截 rich 导入"发现两处**导入期**渲染依赖（`config/validation.py`、`events/listeners.py`）才是真正阻碍；顺带修复命令输出被清屏擦掉的既有缺陷；补 R6/R6b/R6c 护栏。`/api/memory/terminal` 的 parser 合并推迟到 P3 |
| v0.2 | 2026-09-21 | P3 完成：新增 `memory_service` / `persona_service`，`ChatMemory.sync_if_stale()` 补上 CLI 常驻进程缓存失效；D1/D4 消除，`web/routes/{memory,persona}.py` 的 R3 违规清零。**裁决 Q1：保留 `web-` 前缀不改名**（理由与兼容层做法见 §5.3）。执行中发现并修复既有测试污染真实数据库的缺陷，并新增套件级 `data/` 指纹护栏 |
| v0.2 | 2026-09-21 | P4 完成：新增 `llm_config_service` / `rag_service`；**裁决 Q3：字段白名单收敛进 service（D2 消除）**；R3 基线清空（所有 routes 经 services）。密钥 `.env` 落盘有意保留在 Web 侧并说明边界；修正 `test_v011.py` 的 monkeypatch 缝隙 |
| v0.2 | 2026-09-21 | P5 完成：`app/{cli,web,commands}` 整体迁入 `app/interfaces/`，旧目录彻底删除、不留别名（**裁决 Q6**）；入口点与打包范围更新，版本升至 0.2.0，发布包重建。搬迁暴露三类静态检查抓不到的问题：`parents[N]` 层数错误（改为 `app/paths.py::repo_root()` 按标记文件解析）、字符串形式模块名、**已安装的 `xinbot.exe` 入口点需要重装** |
| v0.2 | 2026-09-21 | **P6 完成，全部阶段收尾**：删除命令转发层 `interfaces/commands/handler.py`、`interfaces/cli/chat.py` 空壳与 `chat` 子命令、`start` 的两个 `deprecated` 占位命令、三个空的遗留目录 `app/{static,ui,utils}`；修复 `doctor` 中一条恒为 FAIL 的假警报（检查从不存在的 `prompt template`）。新增"死代码不得复活"契约测试 |
| v0.2 | 2026-09-21 | **端到端验证时发现真实数据污染并修复**：`data/runtime_config.json` 的 `db_path` 曾被测试的 `tmp_path` 覆盖为临时目录，导致应用静默使用临时数据库（用户 11 条对话历史在 UI 中"消失"）。已恢复该字段并实测 Web 端重新可见。护栏补上"跨会话已污染"的预检（原指纹比对只看单次会话前后） |

---

## 14. 全部阶段完成后的最终状态

**测试**：156 → **287 passed**（新增 131 项）
**版本**：0.2.0；发布包 `dist/XinBot-v0.2.0.zip`（119 文件）

### 分层结果

```
app/
├── core/            领域核心（零 UI 依赖，不再 import 任何适配器）
├── services/        跨端业务编排（agent_runtime / memory / persona / llm_config / rag / session）
├── interfaces/      适配器层（cli / web / commands）
├── config/ memory/ storage/ rag/ llm/ events/    基础设施
└── paths.py         仓库根解析（按 pyproject.toml/.git 标记，不再数目录层数）
```

依赖方向 `interfaces → services → core` 由 `tests/test_layering.py` 的
R1–R7 规则与 19 项自测强制执行；`BASELINE` 已清空（无遗留豁免）。

### 五个跨端缺陷（D1–D5）全部消除

| # | 状态 |
|---|------|
| D1 角色-记忆绑定两端分叉 | ✅ 统一为 `PersonaService.activate()` + `memory_name_for_persona()` |
| D2 配置字段白名单只在 Web | ✅ 收敛为 `CONFIG_UPDATE_FIELDS` |
| D3 审批语义两端不一致 | ✅ 改为构造注入 + `approval_mode` 显式暴露 |
| D4 记忆读写路径双份 | ✅ 统一经 `MemoryService`，并补 CLI 缓存失效 |
| D5 `first_mes` 双份实现 | ✅ 收敛为 `AgentRuntime._inject_greeting()` |

### 执行过程中发现并修复的既有缺陷（均不在原计划内）

1. **测试污染真实数据库**：`test_summarizer.py` 未隔离 `db_path`，
   每次跑测试都对用户 `data/xinbot.db` 的 `test_trim` 记忆执行 clear + 写入。
   已修，并加套件级 `data/` 指纹护栏（会话前后比对，污染即失败）。
2. **命令输出被清屏擦掉**：`SessionRunner` 执行命令后又调 `ui.on_start()`，
   而它会 `console.clear()` —— `/help`、`/status` 在桌面宠物 UI 里"闪一下就没"。
3. **配置校验失败看不到原因**：`validate_config` 把明细 print 到终端后只抛一句
   `"Configuration validation failed"`，而调用方全是 `except ValueError`，
   用户永远只能看到"配置无效"。现在异常携带 `.errors` 并逐条展示。
4. **`doctor` 的假警报**：检查一个从不创建的 `prompt template` 文件，恒为 FAIL。
5. **两处导入期渲染依赖**：`config/validation.py` 与 `events/listeners.py` 让
   任何走 `Agent` 的链路（含 Web）都被迫加载 rich。

### 已知遗留（不属于本次重构范围）

- `Pillow` 的 `Image.getdata` 弃用警告（2 处，Pillow 14 移除）。
- `/api/memory/terminal` 的命令名仍是 `list|show|create|...` 而无 `/` 前缀，
  与斜杠命令集并存；合并需改动前端契约，已记于 §6 说明。
- **`data/xinbot.db` 中存在一条 `test_trim` 记忆**（3 条消息，描述 "Memory for test_trim"）。
  它是 P3 之前那个测试隔离缺陷留下的痕迹，未被清理（不主动删除用户目录里的数据）。
  用户可在 Web「记忆」页自行删除。
- `data/runtime_config.json` 的 `persona_name` / `current_memory_name` 当前为
  `xin` / `default`；这只是用户切换过的结果，未作改动。

### ⚠️ P6 期间发现的真实数据污染（已修复 + 已补护栏）

在最后做端到端验证时发现：`/api/memory` 只返回 **1 条空记忆**，
而数据库里实际有 `default`(11 条) 与 `test_trim`(3 条)。
根因是 `data/runtime_config.json` 的 `db_path` 被写成了

```
C:\Users\BTxin\AppData\Local\Temp\tmp7cuteomx\m.db
```

即某个测试用 `RuntimeConfig(db_path=str(tmp_path / "memory.db"))` 构造后
调用了 `save()`，而 `save()` 写的是**全局 `CONFIG_PATH`**（真实配置文件）。
`RuntimeConfig` 的 `db_path` 默认指向真实数据库，所以这个本地单机应用的
对话历史会"凭空消失"——而且是静默的。

**影响范围**：仅 `db_path` 一个字段（`llm_registry.json` 与 `.env` 均未受影响，
已逐项核对）。该配置文件的时间戳显示污染发生在更早的会话。

**已修复**：`db_path` 恢复为 `data/xinbot.db`；实测 Web 端
`/api/memory` 重新返回 `default count: 11`。

**为什么原护栏没抓到**：`tests/data_guard.py` 只比对**单次会话前后**的指纹，
只能发现"本次运行写坏"，无法发现"更早就已经坏了"。

**已补**：新增 `data_guard.precheck()`，在 `pytest_sessionstart` 阶段
检查 `runtime_config.json` / `llm_registry.json` 是否含有测试临时目录特征
（`AppData\Local\Temp\`、`/tmp/`、`pytest-of-` 等），命中即打印醒目的
`DATA PRE-EXISTING POLLUTION` 提示；另有
`test_real_runtime_config_points_into_data_dir` 直接盯住该字段。

**顺带确认**：连续两次完整跑测试后 `runtime_config.json` 哈希不变，
即当前测试套件不会再写真实配置。
