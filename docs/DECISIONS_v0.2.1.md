# xinbot 优化，修复决策书

> 版本：v0.2.1 | 状态：已实施 | 前置：[DECISIONS_V0.2.md](DECISIONS_V0.2.md)（分层重构，P0–P6 已完成）

本轮处理四处问题，外加三项用户提出、原计划外的补强。

---

## 1 角色模型导入问题

### 1.1 问题

用户从外面下载的三个 Live2D 压缩包全部导入失败。实际排查发现它们分属**完全不同的三种形态**：

| 包 | 清单 | 模型 | 动作 | 结果 |
|----|------|------|------|------|
| `Live2d-model-master-...zip` | `*.model3.json` | `.moc3` | `.motion3.json` | Cubism 3/4/5（新） |
| `miku.zip` | `*.model.json` | `.moc` | `.mtn` | Cubism 2.1（旧） |
| `纱雾live2d.zip` | `*.model.json` | `.moc` | `.mtn` + `css/js/images` | 旧版**网页工程包** |

原实现只认 `*.model3.json`，且解压白名单不含 `.moc` / `.mtn` / `.css` / `.js`，
因此后两个包在**解压阶段就被整体拒绝**，报错只有一句"未找到 .model3.json 或 pet.json"，
用户无从判断到底缺什么。

### 1.2 决策

新增 `app/services/live2d_service.py`，把"识别 → 选择 → 校验 → 落盘"从路由里抽出，
CLI 与 Web 共用同一实现。

**格式支持**：

| 格式 | 清单 | 运行时 | 处理 |
|------|------|--------|------|
| Cubism 3/4/5 | `*.model3.json` | `live2dcubismcore.min.js` | 完整支持 |
| Cubism 2.1 | `*.model.json` | `live2d.min.js` | 完整支持（含导入） |
| 精灵图 | `pet.json` + 8×9 网格 | 无 | 完整支持 |

**关键取舍**：

1. **不自动猜缺文件。** 缺 `.moc3`/`.moc`/纹理时报错必须精确到"缺哪个引用"，
   而不是产出一个加载必失败的模型目录。
2. **可选资源只警告不阻断。** 物理、动作、表情缺失时模型仍能显示，
   因此记入 `warnings` 而非报错。
3. **多模型合集可预测地选择。** 优先级 Cubism 3+ → 精灵图 → Cubism 2.1；
   同格式仍有多个则报错并列出候选，**不做语义猜测**。
4. **网页工程包先接受再清理。** `.css/.js/.html/.svg` 允许解压（否则整包被误杀），
   解压后由 `prune_web_assets()` 丢弃与渲染无关的目录。
5. **目录重排。** 无论嵌套多深（如 `合集/游戏/角色/model/`），
   统一落到 `pet/imported/<uuid>/<模型名>/`，不把整条路径带进来。

### 1.3 Cubism 2.1 运行时的授权边界（重要）

`live2d.min.js` 属 Live2D **专有 SDK**，`pixi-live2d-display` 是 MIT 但该 core 不是。
因此：

- **可以**导入并保存旧格式模型；
- **不能**把 `live2d.min.js` 打进发布包；
- 缺失时全链路都要显式告知：`runtime_state()` 带 `ready`/`missing_hint`，
  API 返回 `runtime_ready` 字段，网页外观页显示黄色警告，CLI 提示"缺运行时"。

本机为验证 Cubism 2.1 曾临时下载该文件到 `pet/vendor/`（该目录已被 `.gitignore` 排除）。

### 1.4 前端适配

`Live2DCanvas.vue` 原先硬编码 `pixi-live2d-display/cubism4`。现在按 `pet.format`
选择运行时，并按需加载对应 core（旧格式不必下载新 core，反之亦然）。

注意：两个 runtime 必须**静态导入**——Vite 无法预打包"用变量拼出来的 import 路径"。

---

## 2 服务端运行日志查询

### 2.1 问题

后端出问题时，用户在 CLI 端看不到任何迹象；网页端也没有入口。
唯一线索是 `data/web.log`（进程 stdout 重定向），需要手动翻文件。

### 2.2 决策

新增 `app/logs.py`：**进程内环形缓冲**（默认 500 条）+ 标准 `logging` 接入。

- CLI 与 Web 读**同一份**数据，来源一致；
- 环形缓冲而非写文件：本地单机应用需要的是"最近一段窗口"，无限增长的日志文件
  反而要另配轮转策略；后端退出即清空，不留垃圾；
- `/api/logs`（查询/过滤/清空）、`/api/logs/status`（运行时长、缓冲占用、警告与错误计数）。

**CLI**：`xinbot logs [-n N] [-l LEVEL] [-f]`、`xinbot logs status`、`xinbot logs clear`。

**Web**：导航栏新增"运行日志"页（`/#/logs`），级别筛选 + 2 秒自动刷新 + 状态卡片。

### 2.3 实施中踩到的坑（都已修）

1. **同一条日志被记录两次。** 起初同时给根 logger 和命名 logger 挂 handler，
   而 logger 记录会向父级传播 ⇒ 重复。
   **只挂根 logger** 即可捕获全部（含 `app.*`、`uvicorn.*`）。
2. **uvicorn 的访问日志默认不进缓冲。** 它们使用自己的 logger 且 `propagate=False`，
   需要显式放开。这就是"Web 上看不到 HTTP 请求日志"的原因。
3. **`install()` 幂等判断不能只看模块状态。** 模块被重载或测试重置状态后，
   `_state.installed` 会失真；改为检查 logger 上是否已存在 `BufferHandler`。

### 2.4 后端未运行时的行为

CLI 是独立进程，读不到后端内存。因此 `xinbot logs` 走 HTTP；
后端未运行时明确提示"后端可能未运行"并给出下一步命令，
**而不是打印空列表**让人误以为"没有日志"。

---

## 3 CLI 与文档

### 3.1 新增命令

| 命令 | 作用 |
|------|------|
| `xinbot model import <zip>` | 从命令行导入外观模型（与网页同一套校验） |
| `xinbot model list` | 已导入模型 + 运行时状态 |
| `xinbot model runtimes` | 各格式运行时就绪情况 |
| `xinbot logs [--follow]` | 运行状态与日志 |

### 3.2 文档

- 新增 [命令行手册](CLI.md)：11 个小节，覆盖启动、日志、外观、模型连接、
  角色、记忆、知识库、调试、桌宠内斜杠命令、退出码、常见问题；
- `README.md` 更新到 v0.2.0：新增"支持的外观格式""运行状态与日志"两节，
  补充 v0.1 → v0.2 升级步骤（**必须重装**，入口点已变）；
- `USER_GUIDE.md`：重写"安装和更换桌宠外观"，新增"查看运行状态与日志"与升级章节。

---

## 4 UI 优化

### 4.1 外观页

- 模型卡片显示**格式**（Cubism 3/4/5 与旧版 2.1 可区分）；
- 缺运行时的模型降低透明度并标注"缺运行时"，页面顶部给一条汇总警告；
- 导入成功时把 `warnings` 直接展示（旧格式会提示需要 `live2d.min.js`），
  避免"导入成功但不显示"的困惑；
- 底部说明列出三种格式与命令行等价用法。

### 4.2 运行日志页

新增 `LogsView.vue`：状态卡片（运行时长 / 缓冲占用 / 警告 / 错误）、
级别筛选 chip、等宽字体日志列表、暂停自动刷新、导出与清空。

### 4.3 导航

导航栏增加"外观"与"运行日志"入口。

### 4.4 外观页的删除 / 重命名

模型卡片悬停时右上角出现两个小按钮：重命名、删除。
删除有二次确认，且会同步清理"当前外观"的绑定，避免主页指向不存在的模型。
内置目录（`pet/live2d`、`pet/codexpet`）里的模型不显示这两个按钮——
它们属于发布包资产，不应由界面删除。

---

## 4A ⚠️ 空白页故障（实测发现并修复）

### 4A.1 现象

Web 端整页空白：HTML/CSS/JS 全部返回 200，`<div id="app">` 是空的。
接口全部正常（`/api/status`、`/api/pet/models` 等均 200），
所以**只测接口完全发现不了**。

### 4A.2 根因

上一轮为实现双格式渲染，把两个运行时都做成了**静态 import**：

```js
import { Live2DModel as Live2DModel2 } from 'pixi-live2d-display/cubism2';
import { Live2DModel as Live2DModel4 } from 'pixi-live2d-display/cubism4';
```

而 `cubism2` 模块在**模块求值阶段**就检查 `window.Live2D`，缺失直接抛：

```
Could not find Cubism 2 runtime. This plugin requires live2d.min.js to be loaded.
```

模块顶层抛错 → 整个 bundle 求值失败 → 入口不执行 → 页面空白。

### 4A.3 修复

改为**两个独立的懒加载入口 + 动态 import**：

- `src/live2d/cubism2.js` / `cubism4.js` 各自静态导出对应 `Live2DModel`；
- 组件里用字面量路径 `await import('../live2d/cubism2.js')`，Vite 拆成独立 chunk，
  只有真正要看该格式模型时才求值；
- 加载前先确保对应 core 就绪，缺失时给**可操作**的错误提示而不是白屏。

副作用（正向）：主包从 674 KB 降到 250 KB，两个 runtime 各成 chunk。

### 4A.4 防复发

新增 `app/interfaces/web/tests/smoke.spec.js`：断言 `#app` 有实际内容、
关键界面元素可见、且没有未捕获的 `pageerror`。
这类"后端全绿但前端白屏"的问题必须用浏览器断言 DOM，接口测试无解。

---

## 4B ⚠️ 编辑角色必 500（P1 遗留缺陷）

### 4B.1 现象

`PUT /api/persona/{name}` 抛
`TypeError: AgentRuntime.refresh_persona() missing 1 required positional argument: 'name'`。

### 4B.2 根因

P1 把 `refresh_persona` 写成了**实例方法**（`def refresh_persona(self, name)`），
而路由以 `AgentRuntime.refresh_persona(name)` 调用 —— `name` 被当成 `self`。
当时没有测试覆盖这个路由，缺陷一直潜伏。

### 4B.3 修复与教训

改为 `@classmethod`，并在 `tests/test_agent_runtime_refresh.py` 中
显式以"类调用"形式断言，另有端到端用例跑一遍 `PUT /api/persona/{name}`。

**这个缺陷是靠"日志可视化"发现的**：日志里出现 4 条 `uvicorn.error`
"Exception in ASGI application"。顺带发现日志把堆栈丢了，已修。

### 4B.4 日志补上堆栈

`BufferHandler` 现在检测 `record.exc_info`，把完整 traceback 拼进消息体；
导出文件同样保留。否则 UI 与归档都只剩一句无信息量的
"Exception in ASGI application"。

---

## 5 计划外补强

1. **重复导入去重。** 同一模型被导入多次会产生多个目录。`catalog()` 与 Web 目录
   均按 `(格式, 模型名)` 去重，保留**清单文件修改时间最新**的一份
   （路径含 uuid，排序不能代表新旧）。已清理本机历史上重复导入产生的多余目录。
2. **前端依赖缺失。** `app/interfaces/web/node_modules` 缺少
   `pixi-live2d-display` 与 `pixi.js`（package.json 里有声明但未安装），
   即此前前端 Live2D 渲染本身是不可用的。已 `npm install` 并重新构建。
3. **`doctor` 假警报修复。** 它检查一个从不被创建的 `prompt template` 文件，
   恒为 FAIL（`PromptBuilder` 完全从 `PersonaStore` 生成 prompt）。已移除该检查与空目录。
4. **`favicon.ico` 404。** 浏览器默认请求该文件，服务端没有 → 日志里始终有一条 404 噪音。
   已在 `index.html` 内联空图标（`href="data:,"`）消除。

---

## 6 遗留处理

| 项 | 处理 |
|----|------|
| `data/runtime_config.json` 的 `db_path` 曾被测试写成临时路径 | 已修回 `data/xinbot.db`，并加 `data_guard.precheck()` 防复发 |
| `data/xinbot.db` 中的 `test_trim` 记忆（测试污染遗留） | 已删除；`default` 的 11 条真实对话保留 |
| Pillow `Image.getdata` 弃用警告 | 未处理（Pillow 14 才移除），不影响功能 |
| `/api/memory/terminal` 命令名无 `/` 前缀 | 未合并（需改前端契约），见 DECISIONS_V0.2 §6 |

---

## 7 验证

**359 passed**，发布包 `dist/XinBot-v0.2.0.zip` 重建通过。

新增测试：

- `tests/test_live2d_import.py`（20）：三种格式识别与校验、网页工程包、多模型合集、
  路径穿越、体积限制、**用 `scratch/` 下真实下载包做回归**；
- `tests/test_logs_and_cli.py`（21）：环形缓冲容量/过滤/状态/异常堆栈、`/api/logs` 全套、
  `model import/list/runtimes`、后端未运行时的提示；
- `tests/test_model_management.py`（22）：`remove` 的安全边界与共用容器、
  `rename` 的冲突/非法名/清单同步、Web 删除与改名接口状态码、日志导出（含级别过滤）；
- `tests/test_agent_runtime_refresh.py`（4）：`refresh_persona` 必须能以类方法调用，
  以及 `PUT /api/persona/{name}` 不再 500。

端到端实测（真实启动后端，用 Edge + Playwright 断言 DOM）：

| 页面 | 结果 |
|------|------|
| `/#/` | 渲染正常，`#app` DOM 9.5 KB |
| `/#/appearance` | 5 张模型卡、6 个操作按钮（3 个可管理模型 × 删除/改名） |
| `/#/logs` | 4 张状态卡、导出按钮、50 行日志 |

三个页面 **0 未捕获错误**。另外实测：

- 三个用户压缩包全部导入成功：`abeikelongbi_3`(cubism3)、`miku`(cubism2)、`sagiri`(cubism2)；
- `/api/pet/models` 返回 5 个模型且全部 `runtime_ready: true`，逐个 GET 清单均 200；
- CLI `model rename miku 初音` → 清单变 `初音.model.json`，改名后仍可被浏览器加载；
- CLI `model remove miku -f` → 容器目录一并清理，`list` 只剩其余模型；
- CLI `logs export` → 47 条日志写入文件，带完整日期与表头；
- `PUT /api/persona/{name}` 返回 200，日志中 error 计数为 0。

---

## 8 后续建议

1. **旧格式持久化策略。** 目前靠用户自行放 `live2d.min.js`。若以后要降低门槛，
   可在首次启用旧格式时引导下载（仍需用户确认，不能静默捆绑）。
2. **导入幂等。** 当前重复导入会新建目录（显示时去重、保留最新）。
   彻底幂等需要按内容哈希决定落点，改动面较大，暂未做。
3. **日志持久化。** 已提供按需导出（CLI + 网页）。
   若确实需要开机即写盘，建议加轮转策略而不是常开追加。
