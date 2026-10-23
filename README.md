# AI掘金头条新闻系统 (Toutiao News)

一个基于 **FastAPI + SQLAlchemy** 的现代化新闻系统，包含后端 API 服务（`toutiao_backend`）和前端 Web 应用（`toutiao_frontend`），支持用户注册登录、新闻浏览、收藏、浏览历史，以及基于 MySQL 新闻库的 AI 新闻问答与今日简报。

## ✨ 功能特性

- **用户管理**：注册、登录、信息获取/更新、密码修改
- **新闻模块**：分类列表、新闻列表（分页 + 分类筛选）、详情、浏览量统计
- **收藏模块**：添加/取消收藏、收藏列表、清空收藏
- **浏览历史**：添加记录、历史列表、删除单条、清空历史
- **AI 新闻问答**：基于新闻库 RAG 检索 + ReAct Agent，SSE 流式回答、来源卡片、历史提问（查看/清空）
- **今日新闻简报**：按头条、国内、国际、科技、财经、社会、娱乐、体育分类生成 Markdown 简报
- **缓存优化**：基于 Redis 的新闻详情/列表/分类缓存

## 🧰 技术栈

| 端 | 技术 |
| --- | --- |
| 后端 | FastAPI · SQLAlchemy(异步) · aiomysql · passlib/bcrypt · Redis |
| AI | LangChain · LangGraph · Chroma · OpenAI 兼容接口（Chat + Embedding） |
| 前端 | Vue 3 · Vite · Pinia · Vue Router · Vant · axios · vue-i18n |
| 数据库 | MySQL 8+ · Redis 7+ |

## 📁 项目结构

```
Fastapi/
├── toutiao_backend/            # 后端 API 服务
│   ├── main.py               # 应用入口
│   ├── config/               # 数据库 / Redis 配置
│   ├── models/               # SQLAlchemy 数据模型
│   ├── schemas/              # Pydantic 数据验证模型
│   ├── crud/                 # 数据访问层
│   ├── routers/              # API 路由
│   ├── utils/                # 认证、密码、响应封装等工具
│   ├── ai/                   # AI 新闻问答：RAG / Agent / 工具 / 提示词 / 脚本
│   └── cache/                # Redis 缓存封装
├── toutiao_frontend/           # 前端 Web 应用 (Vue 3)
│   ├── src/
│   │   ├── views/            # 页面组件
│   │   ├── store/            # Pinia 状态管理
│   │   ├── router/           # 路由
│   │   └── config/api.js     # API 地址配置
│   └── package.json
└── requirements.txt            # 后端 Python 依赖
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- MySQL 8+（本地 3306 端口）
- Redis 7+（本地 6379 端口）

### 第一步：准备数据库

1. 安装并启动 MySQL，创建数据库：

```sql
CREATE DATABASE news_app CHARACTER SET utf8mb4;
```

2. 安装并启动 Redis（默认 `localhost:6379`）。

3. （可选）如你的 MySQL 账号/密码与默认不同，修改 `toutiao_backend/config/db_config.py` 中的数据库连接串（默认 `root:123456@localhost:3306/news_app`）。

### 第二步：启动后端

```bash
cd toutiao_backend

# 创建并激活虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux / macOS

# 安装依赖
pip install -r ../requirements.txt

# 启动服务（注意：必须在 toutiao_backend 目录下启动）
uvicorn main:app --reload --port 8000
```

启动成功后，接口文档地址：<http://127.0.0.1:8000/docs>

> ⚠️ 当前版本尚未提供自动建表脚本，数据库表结构定义在 `toutiao_backend/models/` 中，请先手动创建数据表（或等待后续版本补充建表工具）。

### 第三步：启动前端

```bash
cd toutiao_frontend

npm install
npm run dev
```

浏览器访问 Vite 输出的本地地址（默认 <http://localhost:5173>）。前端 API 默认请求 `http://127.0.0.1:8000`，如需修改见 `src/config/api.js`。

### 第四步：初始化 AI 新闻库

1. 在 `toutiao_backend/.env` 中配置模型（不要提交到 git）：

```env
OPENAI_API_KEY=你的模型Key
DASHSCOPE_API_KEY=你的模型Key
BASE_URL=https://你的兼容接口地址/compatible-mode/v1
MODEL_ID=qwen3.8-max
EMBEDDING_MODEL=text-embedding-v4
```

2. 从 MySQL 导出新闻为 txt，并构建 Chroma 向量库：

```bash
cd toutiao_backend

# 导出 ai/data/news/*.txt（内容未变的文件会跳过）
python -m ai.scripts.export_news

# 首次全量建索引；后续增量执行去掉 --rebuild
python -m ai.scripts.build_index --rebuild

# 可选：建完后直接检索验证
python -m ai.scripts.build_index --query "新年贺词"
```

3. 确认 `ai_chat` 表存在（首次部署时手动创建）：

```sql
CREATE TABLE `ai_chat` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int unsigned NOT NULL,
  `message` text NOT NULL,
  `response` text NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_ai_chat_user_idx` (`user_id`),
  CONSTRAINT `fk_ai_chat_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> 新闻新增或修改后，重新执行 `export_news` + `build_index`（增量即可）；删除新闻后 `build_index` 会清理对应向量。

## 📡 API 概览

| 模块 | 接口 | 说明 |
| --- | --- | --- |
| 用户 | `POST /api/user/register` | 注册 |
| 用户 | `POST /api/user/login` | 登录（返回 Token） |
| 用户 | `GET /api/user/info` | 获取用户信息 |
| 用户 | `PUT /api/user/update` | 更新用户信息 |
| 用户 | `PUT /api/user/password` | 修改密码 |
| 新闻 | `GET /api/news/categories` | 新闻分类 |
| 新闻 | `GET /api/news/list` | 新闻列表 |
| 新闻 | `GET /api/news/detail` | 新闻详情 |
| 收藏 | `GET /api/favorite/check` | 检查收藏状态 |
| 收藏 | `POST /api/favorite/add` | 添加收藏 |
| 收藏 | `DELETE /api/favorite/remove` | 取消收藏 |
| 收藏 | `GET /api/favorite/list` | 收藏列表 |
| 收藏 | `DELETE /api/favorite/clear` | 清空收藏 |
| 历史 | `POST /api/history/add` | 添加浏览记录 |
| 历史 | `GET /api/history/list` | 浏览历史列表 |
| 历史 | `DELETE /api/history/delete/{history_id}` | 删除单条记录 |
| 历史 | `DELETE /api/history/clear` | 清空历史 |
| AI | `POST /api/ai/chat` | AI 问答（SSE 流式） |
| AI | `GET /api/ai/chat/history` | AI 历史提问（分页） |
| AI | `DELETE /api/ai/chat/history` | 清空 AI 历史 |

## 🔐 认证方式

登录成功后返回 Token，需要认证的接口在请求头携带：

```
Authorization: <token>
```

Token 有效期为 7 天。
