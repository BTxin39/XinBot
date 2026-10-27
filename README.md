# XinBot v0.2.0

本机 AI 桌宠工作区：左侧 Live2D / Codex 精灵图，右侧聊天、角色卡和记忆管理。

## 使用教学

首次使用请按 [完整使用手册](docs/USER_GUIDE.md) 操作，包含安装启动、首次聊天、
API Key 与 Ollama 配置、角色卡与外观、记忆终端、字符画、端口修改和常见问题。
偏好命令行的用法见 [命令行手册](docs/CLI.md)。

最短上手流程：启动服务 → 左侧“设置”添加连接 → “运行配置”选择模型并应用 →
“角色卡”选择角色并点击“开始对话” → 左侧“对话”发送消息。
语言模型负责回复，角色卡负责性格，桌宠外观负责显示，三者需要分别选择。

## 快速启动

```powershell
xinbot start web             # 网页桌宠：http://127.0.0.1:3796
xinbot start pet             # 桌面常驻桌宠（透明 / 置顶 / 鼠标穿透）
xinbot start cli             # 终端桌宠
xinbot logs --follow         # 另一个终端：实时查看后端运行日志
xinbot start --show          # 查询运行状态、PID 和地址
xinbot start web --shutdown  # 关闭本项目的网页后端
```

`xinbot start` 显示帮助。未激活虚拟环境时使用 `uv run xinbot …`。
`xinbot start web` 在后台启动服务并打开 `http://127.0.0.1:3796/#/`；重复执行会打开已运行的页面，不重复启动。
关闭网页或启动终端不会停止后台服务，请使用 `--shutdown`。进程日志位于 `data/web.log`。
网页地址的端口前是冒号 `:3796`，不是路径 `/3796`。

### 桌面常驻桌宠

```powershell
uv sync --extra desktop      # 首次：装 pywebview（桌宠窗口依赖）
xinbot start pet
```

- 无边框、透明、始终置顶，角色直接浮在桌面上；
- **默认鼠标穿透**：点桌面上的东西不会被挡，只有点在角色身上才响应；
- 左键拖动移动，位置自动记忆；右键菜单可切换置顶/穿透、隐藏或退出；
- 桌面壳只做显示，对话仍走后端，不会出现两个 Agent 抢同一份记忆；
- 仅 Windows，依赖系统自带 WebView2 运行时（Win10/11 通常已安装）。

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。首次安装依赖需要联网。

### 一键安装（推荐给普通用户）

下载 `dist/XinBot-v0.2.0-installer.zip`，解压到想长期使用的目录，然后**右键
`install.ps1` → 使用 PowerShell 运行**。它会自动完成：

1. 检查并安装 uv（不需要管理员权限，装在用户目录）
2. `uv sync --frozen` 安装项目依赖，并安装桌宠窗口依赖
3. 在桌面和开始菜单创建「XinBot 桌宠」快捷方式
4. 双击快捷方式即可启动（无控制台黑窗）

如果系统提示禁止运行脚本，用这条命令绕过（不必关闭全局执行策略）：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

卸载：`.\uninstall.ps1` 只删快捷方式与开机自启，**保留你的数据**；
`.\uninstall.ps1 -Purge` 才会删除 `data\`、`pet\`、`.env`（有二次确认）。

### 从 v0.1 升级到 v0.2

v0.2 把适配器层从 `app/cli`、`app/web` 迁到了 `app/interfaces/`，**控制台入口点也随之改变**。
因此升级后必须重装一次，否则 `xinbot` 会报 `No module named 'app.cli'`：

```powershell
uv sync                 # 或：uv pip install --no-deps -e .
```

用户数据（`data/`、`pet/`、`.env`）无需迁移，保持原位置即可。

下载并解压 `dist/XinBot-v0.2.0.zip`，在目录内运行：

```powershell
./start.ps1
```

也可以直接运行：

```powershell
uv sync --frozen
uv run xinbot start web
```

## 模型与密钥

- 设置页添加 OpenAI-compatible 连接、API 地址、模型 ID 和密钥；可分别增删模型、轮换/删除密钥及删除空连接。
- 当前模型不能直接删除，先在“运行配置”切换；删除连接前先移除所属模型。
- 模型删除只删除 XinBot 注册记录，不删除 Ollama 本机模型权重。
- Ollama：先自行安装并运行 `ollama serve`，在终端执行例如 `ollama pull qwen3:8b`。
  网页选择 Ollama，默认地址 `http://127.0.0.1:11434/v1`，读取本机模型后保存连接，最后在运行配置里选中。
  Ollama 不需要真实 API key；只支持 loopback 地址。工具调用需要模型本身支持。
- Ollama 在本次开发环境中未安装，已使用模拟 HTTP 服务验证模型发现、请求格式和错误处理；未做真实推理验证。

### 密钥安全边界

密钥只保存到项目根目录 `.env`，不回传页面、不存浏览器 localStorage、不写入发布包。
网页不能指定任意环境变量名或文件路径。写入拒绝换行、引号、控制字符和 dotenv 变量表达式，
环境变量名使用服务商标识的哈希，避免名称规范化碰撞。历史连接的环境变量必须以 `_API_KEY` 结尾。
修改已有连接的地址或类型时须重新输入密钥，防止旧密钥被无意转发到其他服务。
远程 API 必须使用 HTTPS；本机端点允许 HTTP。跨站写入和非本机 Host 被拒绝，敏感 API 禁止缓存。

`.env` 是**本机明文文件，不是加密保险库**。POSIX 设置为仅当前用户可读写；Windows 依赖项目目录的 NTFS 权限。
不要放到共享目录或同步盘，不要将服务绑定公网。拥有本机账户、恶意浏览器扩展或文件访问权限的软件仍可能读取它。
网页删除密钥会删除 `.env` 项和当前进程值，不会修改 Windows/父进程已经设置的环境变量；这些值需在系统设置里删除。

## 角色与外观

### v0.1.1 工作台

网页采用左侧 Live2D、右侧聊天布局。右上角工具箱、管理、账户菜单打开可拖动浮窗；账户档案只保存在当前浏览器，不上传服务器。终端只接受 `help`、`status`、`clear` 和 `memory ...` 等受限命令，不执行系统 Shell。

知识源可在导入时指定 TAG，并在知识库页面修改或删除；关系图展示角色、TAG 与知识源的连接。角色卡的“知识库 TAG”决定 Agent 可检索的知识范围；空列表表示不能读取知识库。旧知识源首次用 `default` TAG 查询时自动补标，可在知识库页改成其他 TAG。角色卡原有的酒馆标签与知识库 TAG 分开存储。

“从故事提取角色”支持 UTF-8 TXT、Markdown 和可提取文本的 PDF。文件限制 2 MB，解析文本限制 120000 字，最多预览 12 名角色；候选由 AI 提取，需逐个确认保存，导入前请核对姓名与经历。扫描版 PDF 不支持 OCR。聊天支持 PNG/JPEG/WebP 图片和文本型 PDF（每份最多 2 MB）；图片理解要求当前模型支持视觉输入。深度思考开关通过回答指令调整分析细致度，不保证调用模型原生的推理参数。Enter 发送，Shift+Enter 换行。

桌宠资产统一存放在根目录 `pet/`，整个目录由 `.gitignore` 排除，不纳入发布包。
`pet/live2d/` 为内置 Live2D，`pet/codexpet/` 为 Codex 精灵包，`pet/imported/` 为导入模型，`pet/vendor/` 为运行时 core。
旧版本升级请按 [使用手册的迁移说明](docs/USER_GUIDE.md#10-常见问题与备份) 移动资产，保留内部相对路径。

### 支持的外观格式

外观页与 `xinbot model import` 使用同一套识别与校验逻辑，**不需要手工指定格式**：

| 格式 | 清单文件 | 需要运行时 | 备注 |
|------|----------|-----------|------|
| Live2D Cubism 3/4/5 | `*.model3.json` | `live2dcubismcore.min.js` | 推荐，兼容性最好 |
| Live2D Cubism 2.1（旧版） | `*.model.json` | `live2d.min.js` | 可导入，但需自行放置运行时 |
| Codex 精灵图 | `pet.json` + 8×9 网格图 | 无 | 最省事 |

- **允许压缩包里夹带 `css/js/images` 等网页资源**（Live2DViewerEX 导出包、网页 demo 解包都长这样），
  导入时会自动丢弃与渲染无关的目录；
- 多模型合集（一个 ZIP 里放了整套模型库）会优先取 Cubism 3+，同格式仍有多个则报错并列出候选；
- 深层嵌套目录会被展开为 `pet/imported/<uuid>/<模型名>/`；
- 缺文件时报错会明确指出**缺哪一个引用**（如"模型缺少纹理：textures/texture_00.png"）。

命令行用法：

```powershell
xinbot model import scratch/miku.zip   # 导入
xinbot model list                      # 已导入模型 + 运行时状态
xinbot model rename miku 初音           # 重命名（同步清单文件名）
xinbot model remove 初音                # 删除（只动 pet/imported/）
xinbot model runtimes                  # 各格式运行时就绪情况
```

网页外观页同样可以悬停卡片、点右上角按钮删除或重命名；内置目录（`pet/live2d`、`pet/codexpet`）中的模型不提供这两个操作。

`live2d.min.js`（Cubism 2.1 运行时）属于 Live2D 专有 SDK，**不随本项目分发**。
需要旧版模型时请自行放入 `pet/vendor/live2d.min.js`。Cubism 3/4/5 的 core 可用脚本获取：

```powershell
uv run python scripts/download_live2d.py
```

使用与分发任何第三方模型前，请核对 [Live2D 授权](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html)
与素材作者的要求。

- 兼容原 Persona 数据，支持酒馆 Character Card V2 JSON/PNG 导入、编辑与 JSON 导出。
- 开场白、性格、场景、示例对话和提示词进入 Agent；世界书及未知扩展保留但不执行完整酒馆规则。
- 模型和角色身份可独立绑定。
- 当前是浏览器内桌宠，不包含系统级透明置顶、托盘或点击穿透。

## 运行状态与日志

CLI 与网页看的是**同一个后端进程**的日志，两处内容一致：

```powershell
xinbot logs              # 状态摘要 + 最近 40 条
xinbot logs -n 200       # 更多
xinbot logs -l WARNING   # 只看警告及以上
xinbot logs -f           # 持续跟踪
xinbot logs export -o logs.log   # 导出为文本（含完整日期与表头）
xinbot logs clear        # 清空缓冲
```

网页入口：导航栏 → **运行日志**（`/#/logs`），支持级别筛选、自动刷新与导出。
日志保存在内存环形缓冲（默认 500 条），不写文件、不无限增长；后端退出即清空。
异常日志会带完整堆栈。后端未运行时 CLI 会提示"后端可能未运行"并给出下一步命令，而不是打印空列表。

## 记忆管理

记忆页支持创建、切换、查看消息、清空消息、删除、导出，以及编辑长期事实、用户偏好和摘要。
切换角色会切换到该角色默认记忆；记忆页可手动选择其他会话。当前记忆不可直接删除。
消息只保存配置窗口内的记录，不应当作无限聊天归档；运行摘要目前不跨重启持久化。

交互控制台是**受限的记忆命令终端，不是系统 Shell**，不需要安装额外终端软件：

```text
help
list
create study
use study
show study
describe study "学习记录"
clear study
use default
delete study
```

支持上下方向键历史命令和破坏性操作确认，不执行 PowerShell、CMD、文件命令或 Python。
长期记忆为本机数据；导出文件可能含个人信息，请自行保护。

## 图片转字符画

“字符画”页面上传图片，选择 Braille / ASCII 和宽度，可预览、复制、下载文本。
复用 `app/services/image_ascii.py`；上传只使用临时文件，转换后清理。限制 10 MB、1600 万像素。

## 配置与端口

设置页“运行配置”提供模型、温度、记忆窗口、端口及网页搜索开关。
知识库目前使用 Chroma 默认嵌入器，不开放无效的 Embedding 模型切换项。
端口范围 1024–65535；修改端口保存后**重启后端生效**，当前连接不被强制中断。
也可临时覆盖：`uv run xinbot start web --port 4000`。监听地址固定为 `127.0.0.1`。
MCP 启动命令、数据库路径和任意环境变量不开放网页修改，以免引入远程执行/文件写入入口。

## 开发与验证

源码开发另需 Node.js 20+：

```powershell
uv sync --frozen
cd app/interfaces/web
npm ci
npm run build
cd ../..
uv run xinbot start web
uv run pytest tests -q
```

开发时运行 `xinbot start web --dev` 和 `npm run dev`。Vite 启动时读取保存的端口，
也可用 `XINBOT_WEB_PORT` 覆盖；修改端口后需重启 Vite。前端始终使用同源 API/WebSocket。
浏览器测试：在后端启动后进入 `app/interfaces/web` 运行 `npx playwright test --workers=1`，默认使用 Microsoft Edge。
测试不调用付费模型、不修改真实记忆，也不会写真实 `data/`（有套件级护栏检查）。
更多兼容说明见 `docs/WEB_COMPANION.md`。

## 构建发布包

```powershell
cd app/interfaces/web
npm ci
npm run build
cd ../..
uv run python scripts/package_release.py
```

产物：`dist/XinBot-v0.2.0.zip`、对应 SHA256 校验文件；包内 `MANIFEST.json` 列出文件哈希。
打包脚本使用允许清单，不读取 `.env`、`data/`、`pet/`、上传模型、日志、缓存或 `node_modules`。
干净目录首次启动从内置公开默认角色生成数据，不携带开发者的私有角色卡。

## 注意事项

- 发布包可能滞后于源码，遇到问题请优先使用源码运行。
- v0.2.0 更换了 CLI 入口点，升级后必须重装依赖（见上文"从 v0.1 升级"）。
