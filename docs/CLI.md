# XinBot 命令行手册（CLI Manual）

> 适用版本：v0.2.0+
> 所有命令都在项目根目录执行。已激活虚拟环境时用 `xinbot`，否则用 `uv run xinbot`。

## 0. 一分钟上手

```powershell
uv sync --frozen          # 首次安装依赖（需要联网）
xinbot doctor             # 自检：配置、密钥、注册表、记忆是否就绪
xinbot start web          # 启动网页后端（http://127.0.0.1:3796）
xinbot logs --follow      # 另开一个终端，实时看后端在做什么
xinbot start cli          # 或不打开网页，直接用终端桌宠聊天
```

三个容易混淆的"模型"概念（详见 [使用手册](USER_GUIDE.md#2-分清三个模型概念)）：

| 说法 | 是什么 | 怎么配 |
|------|--------|--------|
| 语言模型 | 负责生成回复的 LLM | `xinbot config set-model` 或网页"设置" |
| 角色卡 | 决定性格、开场白 | `xinbot persona set` 或网页"角色" |
| 桌宠外观 | 决定 Live2D / 精灵图长相 | `xinbot model import` 或网页"外观" |

## 1. 启动与状态

| 命令 | 说明 |
|------|------|
| `xinbot start` | 显示 `start` 的帮助 |
| `xinbot start cli` | 终端桌宠（Rich UI，斜杠命令对话） |
| `xinbot start web` | 后台启动网页后端并打开浏览器 |
| `xinbot start web --dev` | 开发模式（不托管前端构建产物，配合 Vite） |
| `xinbot start web --port 4000` | 本次用指定端口 |
| `xinbot start web --shutdown` | 关闭本项目启动的后端 |
| `xinbot start --show` | 查询是否在运行、PID 与地址 |

`start web` 会在后台起一个受管子进程，关闭浏览器**不会**停止它，请用 `--shutdown`。

常用参数（`start cli`）：

```powershell
xinbot start cli                    # 默认宠物
xinbot start cli -m gpt-4.1         # 本次临时换模型
xinbot start cli -p openai          # 本次临时换服务商
xinbot start cli -i cat.png         # 用图片转 braille 作为宠物图案
```

## 2. 运行状态与日志（新增）

CLI 与网页看的是**同一个后端进程**的日志，来源一致。

| 命令 | 说明 |
|------|------|
| `xinbot logs` | 运行状态摘要 + 最近 40 条日志 |
| `xinbot logs -n 200` | 最近 200 条 |
| `xinbot logs -l WARNING` | 只看 WARNING 及以上 |
| `xinbot logs -f` / `--follow` | 持续跟踪（Ctrl+C 退出） |
| `xinbot logs status` | 只看状态摘要 |
| `xinbot logs export [-o 文件] [-n N]` | 导出为文本文件（含完整日期与表头） |
| `xinbot logs clear` | 清空后端日志缓冲 |

输出示例：

```
后端运行状态  已运行 2分13秒  缓冲 46/500  警告 0  错误 0
17:37:08 INFO    uvicorn.access "GET /api/status HTTP/1.1" 200
17:37:13 WARNING app.services.llm_config_service 未找到模型，回落到默认
```

网页端对应入口：导航栏 → **运行日志**（`/#/logs`），支持按级别筛选、2 秒自动刷新，
以及**导出**按钮（下载 `.log` 文件）。

导出文件带完整日期与表头，适合归档后回溯：

```
# XinBot 运行日志导出
# 导出时间：2026-10-17 17:59:04
# 记录条数：47 / 缓冲 47/500
# 警告 0 条，错误 4 条
# 格式：时间 | 级别 | logger | 内容

2026-10-17 17:58:40 | INFO    | xinbot | XinBot Web 后端已启动
```

异常日志会带上完整堆栈（否则只有一句 "Exception in ASGI application"，
等于没法定位）。

> 后端未运行时 `xinbot logs` 会提示"后端可能未运行"并给出下一步命令，而不是打印空列表。

## 3. 桌宠外观模型（新增）

支持三种格式，且**允许压缩包里带额外的 css/js/images 等网页资源**（Live2DViewerEX
导出包、网页 demo 解包都是这种形态）：

| 格式 | 清单文件 | 需要运行时 | 说明 |
|------|----------|-----------|------|
| Live2D Cubism 3/4/5 | `xxx.model3.json` | `live2dcubismcore.min.js` | 新版，推荐 |
| Live2D Cubism 2.1 | `xxx.model.json` | `live2d.min.js` | 旧版，见下方授权说明 |
| Codex 精灵图 | `pet.json` + 8×9 网格图 | 无 | 最省事 |

| 命令 | 说明 |
|------|------|
| `xinbot model import <zip>` | 从 ZIP 导入一个外观 |
| `xinbot model list` | 列出已导入的模型及其运行时状态 |
| `xinbot model rename <旧名> <新名>` | 重命名（同步清单文件名） |
| `xinbot model remove <名字> [-f]` | 删除（只动 `pet/imported/` 下的内容） |
| `xinbot model runtimes` | 查看各格式的运行时是否就绪 |

导入示例：

```powershell
xinbot model import scratch/miku.zip
xinbot model import "D:\downloads\character.zip" -q   # -q 只输出结果
```

重命名与删除：

```powershell
xinbot model rename miku 初音            # 目录与清单文件名一起改
xinbot model remove 初音 -f               # -f 跳过确认
```

删除的安全边界：

- 只允许删除 `pet/imported/` 下的模型；`pet/live2d/`、`pet/codexpet/` 等内置目录不受影响；
- 若一个目录里手工塞了多个模型，只删目标，保留容器与其它模型；
- 网页外观页对同样可管理的模型提供删除/改名按钮（悬停卡片右上角）。

导入规则（CLI 与网页完全一致）：

- 自动识别格式，**不需要**手工指定；
- 压缩包内只有一个模型 → 直接导入；
- 有多个模型 → 优先 Cubism 3+，其次精灵图，最后 Cubism 2.1；
  同格式仍有多个则报错并列出候选，请自行裁剪压缩包后重试；
- 深层嵌套目录（如 `a/b/c/model/`）会被展开到 `pet/imported/<uuid>/<模型名>/`；
- 缺少必需文件（`.moc3`/`.moc`/纹理）会精确报告**缺哪一个引用**，而不是笼统失败。

### 关于 Cubism 2.1 的运行时

`live2d.min.js` 属于 Live2D 专有 SDK，**不随本项目分发**（`pixi-live2d-display`
本身是 MIT，但该 core 不是）。因此：

- **可以**导入并保存 Cubism 2.1 模型；
- 必须自行把 `live2d.min.js` 放到 `pet/vendor/` 才能显示；
- 缺失时 `xinbot model list` 会标注"缺 runtime"，网页外观页会显示黄色警告。

Cubism 3/4/5 的 core 可以用脚本获取：

```powershell
uv run python scripts/download_live2d.py
```

使用与分发任何第三方模型前，请自行核对
[Live2D 授权](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html)
与素材作者的要求。

## 4. 语言模型与连接

```powershell
xinbot config providers                 # 列出已注册服务商
xinbot config provider-types            # 支持的 provider 类型
xinbot config add-provider NAME --api_key_env ENV [--base_url URL] [--type openai-compatible]
xinbot config remove-provider NAME
xinbot config models                    # 列出已注册模型
xinbot config add-model NAME -p PROVIDER
xinbot config set-model deepseek-v4-flash   # 切换当前模型（会校验服务商匹配）
xinbot config set-provider deepseek
xinbot config remove-model NAME
xinbot config show                      # 当前运行配置
```

要点：

- 不能删除**正在使用**的模型或服务商，先切换；
- 服务商仍有模型时不能删除，先移除模型；
- 网页端的"设置"页与这些命令走同一套校验（`LLMConfigService`），行为一致；
- API Key 由网页写入 `.env`；CLI 通过环境变量读取，不写 `.env`。

## 5. 角色卡

```powershell
xinbot persona list
xinbot persona show [NAME]
xinbot persona set NAME            # 切换角色（同时切到该角色的专属记忆）
xinbot persona add NAME -d "显示名" -t "特点1,特点2" -s "说话风格" -b "背景"
xinbot persona edit NAME [--display ...] [--traits ...]
xinbot persona remove NAME -f
xinbot persona emotions
xinbot prompt show [NAME]          # 预览完整 System Prompt
xinbot prompt preview [NAME] -e happy
```

> `persona set` 会把当前记忆切到 `web-<角色名>`，这是设计行为（每个角色独立对话历史）。

## 6. 记忆

```powershell
xinbot memory list                 # 所有记忆，标注当前
xinbot memory create -n study -d "学习记录"
xinbot memory switch -n study
xinbot memory info [-n NAME]
xinbot memory read [-r NAME]       # 读消息历史
xinbot memory clear [-n NAME]      # 清空消息（保留描述）
xinbot memory update [-n NAME] -d "新描述"
xinbot memory delete -n NAME       # 不能删除当前记忆
```

网页端"记忆"页与交互终端（`help`/`list`/`use`/`clear`…）都能做同样的事。

## 7. 知识库（RAG）

```powershell
xinbot rag ingest <文件或目录> [-t TAG]
xinbot rag ingest-url <URL> [-t TAG]
xinbot rag search "查询" -k 5
xinbot rag list
xinbot rag stats
xinbot rag remove <来源>
xinbot rag clear -f                # -f 跳过确认
```

标签用于按角色过滤：角色卡的"知识库 TAG"决定它能看到哪些知识源。

## 8. 调试与自检

```powershell
xinbot doctor                      # 配置自检（路径、服务商、模型、密钥、记忆）
xinbot status                      # Agent 状态（情绪、模型、消息数）
xinbot debug                       # 纯文本调试对话，无 Rich UI
xinbot version
```

`doctor` 全部 OK 后再排查别的问题；它不检查网络连通性。

## 9. 终端桌宠内的斜杠命令

`xinbot start cli` 进入对话后，输入以 `/` 开头的命令（不会发给模型）：

| 命令 | 说明 |
|------|------|
| `/help` | 命令列表 |
| `/clear` | 清空当前会话记忆 |
| `/history [N]` | 最近 N 条对话（默认 10） |
| `/status` | Agent 状态 |
| `/config` | 运行配置 |
| `/remember` | 把当前对话提炼进长期记忆 |
| `/happy` `/sad` `/angry` `/sleepy` `/normal` | 切换情绪表情 |

输入 `exit` 或 `quit` 退出（会保存记忆）。

## 10. 退出码约定

| 退出码 | 含义 |
|--------|------|
| `0` | 成功 |
| `1` | 参数/配置/运行态错误（已打印可读原因） |

脚本里可以这样判断：

```powershell
xinbot doctor; if ($LASTEXITCODE -ne 0) { Write-Error "配置未就绪" }
```

## 11. 常见问题

| 现象 | 原因与处理 |
|------|-----------|
| `xinbot` 报 `No module named 'app.cli'` | v0.2.0 改了入口点到 `app.interfaces.cli`，请重装：`uv pip install --no-deps -e .` 或 `uv sync` |
| `xinbot logs` 提示后端未运行 | 先 `xinbot start web`；或 `xinbot start --show` 确认 |
| 旧版 Live2D 导入后不显示 | 缺 `pet/vendor/live2d.min.js`，见 §3 |
| 导入报"压缩包含多个模型" | 一个 ZIP 里放了整套模型库，裁剪成单个模型后重试 |
| 端口被占用 | `xinbot start web --port 4000`，或在设置页改端口后重启 |

更多内容见 [完整使用手册](USER_GUIDE.md) 与 [Web 兼容说明](WEB_COMPANION.md)。
