# XinBot v0.1.0

本机 AI 桌宠工作区：左侧 Live2D / Codex 精灵图，右侧聊天、角色卡和记忆管理。

## 使用教学

首次使用请按 [完整使用手册](docs/USER_GUIDE.md) 操作，包含安装启动、首次聊天、
API Key 与 Ollama 配置、角色卡与外观、记忆终端、字符画、端口修改和常见问题。

最短上手流程：启动服务 → 左侧“设置”添加连接 → “运行配置”选择模型并应用 →
“角色卡”选择角色并点击“开始对话” → 左侧“对话”发送消息。
语言模型负责回复，角色卡负责性格，桌宠外观负责显示，三者需要分别选择。

## 快速启动

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。首次安装依赖需要联网。

下载并解压 `dist/XinBot-v0.1.0.zip`，在目录内运行：

```powershell
./start.ps1
```

也可以直接运行：

```powershell
uv sync --frozen
uv run xinbot start web
```

打开 http://127.0.0.1:3796。发行 ZIP 已包含构建后的前端，不需要 Node.js。
这是源码运行包，不是独立 EXE；不包含 Python、依赖、私有配置、聊天记录或第三方模型。

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

桌宠资产统一存放在根目录 `pet/`，整个目录由 `.gitignore` 排除，不纳入发布包。
`pet/live2d/` 为 Live2D，`pet/codexpet/` 为 Codex 精灵包，`pet/imported/` 为网页导入模型，`pet/vendor/` 为 Cubism Core。
旧版本升级请按 [使用手册的迁移说明](docs/USER_GUIDE.md#10-常见问题与备份) 移动资产，保留内部相对路径。

- 兼容原 Persona 数据，支持酒馆 Character Card V2 JSON/PNG 导入、编辑与 JSON 导出。
- 开场白、性格、场景、示例对话和提示词进入 Agent；世界书及未知扩展保留但不执行完整酒馆规则。
- 外观页支持 Live2D ZIP 和 Codex 8×9 精灵图包。模型和角色身份可独立绑定。
- 下载官方 Haru 测试模型及 Cubism Core：`uv run python scripts/download_live2d.py`。
  第三方资产不包含在 v0.1 ZIP 中，使用与分发前须核对 [Live2D 授权](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html)。
- 当前是浏览器内桌宠，不包含系统级透明置顶、托盘或点击穿透。

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
复用 `app/cli/image_to_ascii.py`；上传只使用临时文件，转换后清理。限制 10 MB、1600 万像素。

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
cd app/web
npm ci
npm run build
cd ../..
uv run xinbot start web
uv run pytest tests/test_web_cards.py tests/test_web_management.py -q
```

开发时运行 `xinbot start web --dev` 和 `npm run dev`。Vite 启动时读取保存的端口，
也可用 `XINBOT_WEB_PORT` 覆盖；修改端口后需重启 Vite。前端始终使用同源 API/WebSocket。
浏览器测试：在后端启动后进入 `app/web` 运行 `npx playwright test --workers=1`，默认使用 Microsoft Edge。
测试不调用付费模型、不修改真实记忆。更多兼容说明见 `docs/WEB_COMPANION.md`。

## 构建 v0.1 发布包

```powershell
cd app/web
npm ci
npm run build
cd ../..
uv run python scripts/package_release.py
```

产物：`dist/XinBot-v0.1.0.zip`、对应 SHA256 校验文件；包内 `MANIFEST.json` 列出文件哈希。
打包脚本使用允许清单，不读取 `.env`、`data/`、`pet/`、上传模型、日志、缓存或 `node_modules`。
干净目录首次启动从内置公开默认角色生成数据，不携带开发者的私有角色卡。
