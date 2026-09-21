# XinBot Web + Desktop Pet 技术决策书

> 版本: v0.1 | 日期: 2026-07-18 | 状态: 正在实施
>
> 本文档记录 XinBot 从 CLI 阶段进入 Web + 桌面宠物阶段的所有关键技术决策。
> 后续开发严格以此文档为准，如有变更需同步更新本文档。

---

## 1. 全局架构

### 1.1 决策：单体多进程

**选中：单体多进程** — `xinbot start web` 一个命令启动全部

```
xinbot start web
  ├── FastAPI 后端 (主进程, :3796)
  ├── Vite 开发服务器 (子进程, :5173, 仅开发模式)
  │   └── Vue 3 前端 SPA
  ├── BongoCat 桌面悬浮窗 (子进程, pygame, 可选 --no-pet 跳过)
  └── Agent 单例 (所有请求共享)
```

- 生产模式：FastAPI serve 前端 build 产物，不启动 Vite
- 开发模式：同时启动 Vite dev server + FastAPI (CORS 代理)

### 1.2 组件关系图

```
xinbot start web
    │
    ├──> FastAPI :3796 ---- Agent (核心单例)
    │       ▲                  │
    │       │ REST/WS          ├─ PersonaStore (JSON)
    │       │                  ├─ KnowledgeBase (ChromaDB)
    │       ▼                  ├─ MemoryManager (SQLite)
    │   浏览器 (Vue 3 SPA)      └─ ToolRegistry
    │       │
    │       ├── Live2D Canvas (用户自定义模型)
    │       ├── 对话界面 (WebSocket流式)
    │       ├── 设置面板 (REST)
    │       ├── 角色管理 (REST)
    │       └── RAG管理 (REST)
    │
    └──> Pygame 窗口 (子进程 **暂时搁置**)
            ├── 透明无边框
            ├── 鼠标穿透
            ├── 窗口置顶
            └── HTTP轮询 GET /api/pet/state
```

### 1.3 关键约束

- **不引入外部认证**：本地桌面应用，无登录/注册
- **不引入消息队列**：组件间用 HTTP + WebSocket 通信
- **不引入独立数据库迁移**：复用现有 SQLite + JSON 存储  
- **Python >= 3.12**：与现有项目一致

---

## 2. FastAPI Web 后端

### 2.1 决策概要

| 决策项 | 选择 |
|--------|------|
| 入口 | `xinbot start web` |
| 端口 | 3796 |
| Agent 生命周期 | 服务级单例 |
| 前端服务 | 开发: 代理 Vite :5173 / 生产: serve dist/ |

### 2.2 API Endpoints

#### REST

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/status | Agent 状态（情绪、模型、provider） |
| POST | /api/chat | 非流式对话 |
| GET | /api/config | 获取配置 |
| POST | /api/config | 更新配置 |
| GET | /api/persona | 列出 persona |
| POST | /api/persona | 创建 persona |
| PUT | /api/persona/{name} | 更新 persona |
| DELETE | /api/persona/{name} | 删除自定义 persona |
| GET | /api/rag/sources | 知识库来源列表 |
| POST | /api/rag/ingest | 导入文档 |
| POST | /api/rag/ingest-url | 导入网页 |
| POST | /api/rag/search | 搜索知识库 |
| DELETE | /api/rag/sources/{id} | 删除知识来源 |
| DELETE | /api/rag/clear | 清空知识库 |
| GET | /api/pet/state | 桌面宠轮询端点 |

#### WebSocket

| 路径 | 说明 |
|------|------|
| /ws/chat | 流式对话：send `{"message":"..."}` -> recv `{"chunk":"..."}` ... `{"done":true}` |

#### 统一响应格式

```json
{"ok": true, "data": {...}}
{"ok": false, "error": "..."}
```

### 2.3 Agent 单例管理

```python
class AgentManager:
    _instance: Agent | None = None

    @classmethod
    def get(cls) -> Agent:
        if cls._instance is None:
            cls._instance = Agent(RuntimeConfig.load())
        return cls._instance

    @classmethod
    def reload(cls) -> Agent:
        cls._instance = None
        return cls.get()
```

### 2.4 现有 backend 骨架处理

**决策：删除 `app/backend/`，Web 代码统一放在 `app/web/`。**

理由：早期骨架与当前 Agent 核心不联通、不需要用户系统、避免维护两套 ORM。

---

## 3. Web 前端

### 3.1 决策：Vue 3 + Vite

**选中：Vue 3 + Vite** — 组件化开发，SFC 单文件组件

| 决策项 | 选择 |
|--------|------|
| 框架 | Vue 3 (Composition API) |
| 构建 | Vite |
| 路由 | Vue Router (hash mode) |
| Live2D | Cubism SDK 4 for Web (npm 引入) |
| 代码高亮 | highlight.js |
| Markdown | marked.js |

### 3.2 项目结构

```
app/web/
├── static/                  # FastAPI serve 的根目录
│   ├── dist/                # Vite build 产物 (生产)
│   └── models/              # Live2D 模型 (用户放入)
│       └── .gitkeep
├── src/                     # Vue 源码
│   ├── main.js
│   ├── App.vue
│   ├── router.js
│   ├── api.js               # axios/fetch 封装
│   ├── components/
│   │   ├── Live2DView.vue   # Live2D 渲染
│   │   ├── ChatPanel.vue    # 对话界面
│   │   ├── MessageBox.vue   # 消息气泡
│   │   ├── SettingsPanel.vue
│   │   ├── PersonaManager.vue
│   │   ├── RagManager.vue
│   │   └── TopBar.vue       # 顶部导航
│   ├── composables/
│   │   └── useWebSocket.js  # WebSocket hook
│   └── assets/
│       └── styles.css
├── index.html               # Vite 入口
├── package.json
└── vite.config.js
```

### 3.3 路由设计

| 路径 | 组件 | 说明 |
|------|------|------|
| / | ChatPanel + Live2DView | 主页：对话 + 桌宠 |
| /settings | SettingsPanel | 设置（模型/provider等） |
| /persona | PersonaManager | 角色管理 |
| /rag | RagManager | RAG 知识库管理 |

### 3.4 页面布局

```
┌──────────────────────────────────────────────────────┐
│  [对话] [设置] [角色] [知识库]                         │ <- TopBar
│  ┌──────────────┐  ┌───────────────────────────────┐ │
│  │              │  │                               │ │
│  │   Live2D     │  │   对话区域                     │ │
│  │   画布       │  │                               │ │
│  │  (常驻左侧)  │  │   Xin: 你好呀~                │ │
│  │              │  │   You: 今天天气不错            │ │
│  │  300x400     │  │   Xin: 是呢！                 │ │
│  │              │  │                               │ │
│  │              │  │  ┌────────────────────────┐   │ │
│  │              │  │  │  输入消息...      [发送] │   │ │
│  │              │  │  └────────────────────────┘   │ │
│  └──────────────┘  └───────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

- Live2D 常驻左侧 300px 宽
- 右侧是 Vue Router 切换内容
- 非主页路由（设置/角色/知识库）Live2D 缩小到右下角浮动

### 3.5 开发/生产模式

```
开发: xinbot start web --dev
  ├── Vite :5173 (HMR 热更新)
  └── FastAPI :3796 代理 /api/* 到后端

生产: xinbot start web
  └── FastAPI :3796 serve dist/ + /api/*
```

---

## 4. BongoCat 桌面悬浮窗(搁置)

### 4.1 决策：pygame + HTTP 轮询

| 决策项 | 选择 |
|--------|------|
| 渲染引擎 | pygame (透明窗口 + SRCALPHA) |
| 通信方式 | HTTP 轮询 GET /api/pet/state (1秒间隔) |
| 默认素材 | ASCII 渲染为 Surface (无外部依赖) |
| 可选素材 | data/pet/*.png (用户放入则优先使用) |

### 4.2 核心特性

| 特性 | 实现方式 |
|------|---------|
| 透明无边框 | pygame.NOFRAME + SRCALPHA surface |
| 鼠标穿透 | win32api: WS_EX_TRANSPARENT + WS_EX_LAYERED |
| 窗口置顶 | SetWindowPos(HWND_TOPMOST) |
| 可拖拽 | 检测鼠标在宠物像素区域 -> 临时关穿透 -> 拖拽 -> 恢复 |
| 情绪联动 | 轮询 /api/pet/state，根据 emotion 切换表情 |
| 消息气泡 | 新消息到达时头顶显示文本框 (2.5秒消失动画) |

### 4.3 视觉表现

**默认模式**：读取 ascii_pets.py 的 Q 版图案 -> pygame.font 渲染
**图片模式**：检测 data/pet/{emotion}.png -> 存在则加载为 Surface

### 4.4 状态轮询响应

```json
// GET /api/pet/state
{
  "emotion": "happy",
  "persona_name": "Shiro",
  "latest_message": "今天天气真好~",
  "has_new_message": true,
  "timestamp": 1766438400
}
```

### 4.5 鼠标交互

```
默认: 窗口穿透，鼠标事件透传给下方程序
鼠标移到宠物身上: 检测 Surface alpha>0 -> 临时取消穿透
  拖拽: 移动窗口位置
  右键: 弹出菜单 [切换表情 / 打开Web / 退出]
  离开: 恢复穿透
```

### 4.6 文件结构

```
app/pet/
├── __init__.py
├── window.py           # 主窗口 (pygame 循环)
├── renderer.py         # 渲染 (ASCII/font -> Surface)
└── api_client.py       # HTTP 客户端 (轮询 + 重连)
```

---

## 5. 数据流总结

```
浏览器 --WebSocket--> FastAPI --agent.stream_chat()--> LLM
   <--{chunk}--------  后端      <--yield-------------

浏览器 --POST /api/config--> FastAPI --save + reload()--> Agent
   <--{ok}--------------

pygame --GET /api/pet/state--> FastAPI --读取 Agent.state.emotion
   <--{emotion, message}---   后端       + latest_message
```

---

## 6. 实施阶段

| 阶段 | 内容 | 预估 |
|------|------|------|
| Phase 1 | FastAPI 后端 (routes + WebSocket + AgentManager) | ~8 文件 |
| Phase 2 | Vue 3 前端 (组件 + 路由 + WebSocket 对话) | ~12 文件 |
| Phase 3 | Pygame 桌面宠 (窗口 + 渲染 + 轮询) | ~4 文件 |
| Phase 4 | 集成联调 + 清理 backend 目录 + 测试 | - |

---

## 7. 依赖变更

### 新增 Python

```toml
pygame>=2.6             # 桌面悬浮窗
uvicorn[standard]>=0.35 # ASGI server
python-multipart>=0.0.20 # 文件上传
aiofiles>=25.1          # 异步文件IO
```

### 新增前端 (package.json)

```json
{
  "vue": "^3.5",
  "vue-router": "^4.5",
  "vite": "^6",
  "@vitejs/plugin-vue": "^5",
  "marked": "^15",
  "highlight.js": "^11"
}
```

---

## 8. 假设与默认

| # | 假设 |
|---|------|
| 1 | Web 仅本地访问 (127.0.0.1:3796)，不暴露公网 |
| 2 | 不处理多用户会话，Agent 全局单例 |
| 3 | 前端需先 npm install + npm run build 才能生产使用 |
| 4 | 桌宠资产统一放入根目录 pet/：live2d/、codexpet/、imported/、vendor/；整个 pet/ 不纳入 Git 和发布包 |
| 5 | 桌面宠默认 ASCII 渲染，可选覆盖 PNG |

## 9. Web Companion 适配补充

- Web 使用左侧常驻桌宠、右侧聊天/管理工作区；手机使用上下布局。
- 接入真正的 Cubism Live2D 渲染和本地 Codex 8x9 精灵图模型；官方 Haru 样例仅用于本地测试，发布前须核对授权。
- 原 Persona 格式保持兼容，新增 Character Card V2 JSON/PNG 导入、JSON 导出、完整字段编辑及角色外观绑定。
- 切换角色使用独立消息记忆。世界书和未知扩展保留，但不执行酒馆脚本或完整世界书规则。
- 服务商、模型 ID、API 密钥由网页管理；密钥仅保存在本机 `.env`，不回传浏览器。
- Web 启动不依赖预先配置密钥；Agent 懒加载，危险工具默认拒绝。
- 本阶段完成浏览器内桌宠，不包括系统级透明置顶桌面窗口。
- 运行、测试、授权和兼容边界见 `docs/WEB_COMPANION.md`。
