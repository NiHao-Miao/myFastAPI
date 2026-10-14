# AI掘金头条新闻系统 (Toutiao News)

一个基于 **FastAPI + SQLAlchemy** 的现代化新闻系统，包含后端 API 服务（`toutiao_backend`）和前端 Web 应用（`toutiao_frontend`），支持用户注册登录、新闻浏览、收藏、浏览历史等功能。

## ✨ 功能特性

- **用户管理**：注册、登录、信息获取/更新、密码修改
- **新闻模块**：分类列表、新闻列表（分页 + 分类筛选）、详情、浏览量统计
- **收藏模块**：添加/取消收藏、收藏列表、清空收藏
- **浏览历史**：添加记录、历史列表、删除单条、清空历史
- **缓存优化**：基于 Redis 的新闻详情/列表/分类缓存

## 🧰 技术栈

| 端 | 技术 |
| --- | --- |
| 后端 | FastAPI · SQLAlchemy(异步) · aiomysql · passlib/bcrypt · Redis |
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

## 🔐 认证方式

登录成功后返回 Token，需要认证的接口在请求头携带：

```
Authorization: <token>
```

Token 有效期为 7 天。

## 📄 更多文档

- `API接口规范文档.md` — 接口详细规范
- `项目后端设计说明文档.md` — 架构与数据库设计说明
