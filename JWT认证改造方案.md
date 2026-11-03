# JWT 认证改造方案

> 项目：`HelloFastAPI`（`toutiao_backend` + `toutiao_frontend`）
> 目标：把当前“UUID 随机字符串 + 数据库查表”的登录凭证，升级为“JWT Access Token + 随机 Refresh Token”的双令牌认证。
> 阅读方式：第 1～4 章讲清楚“为什么”和“改成什么样”，第 5～8 章是可以照着敲的“怎么做”，第 9～11 章是排错、安全加固和回滚。
> 重要：本文只给方案和参考代码，不会直接修改你的项目文件。你可以按步骤逐段复制。

---

## 0. 先看结论（TL;DR）

改造后的认证由两个令牌组成：

| 令牌 | 格式 | 有效期 | 存放位置 | 作用 |
| --- | --- | --- | --- | --- |
| Access Token（访问令牌） | JWT（HS256 签名） | 30 分钟 | 前端内存 + localStorage | 每次请求放在 `Authorization: Bearer <token>` 里 |
| Refresh Token（刷新令牌） | 64 位随机字符串 | 7 天 | 前端 localStorage；数据库只存 SHA-256 哈希 | 访问令牌过期后，用它换新的访问令牌；可被服务端撤销 |

核心改动只有三件事：

1. **登录/注册**：不再生成 UUID 写数据库，而是生成 JWT 访问令牌 + 随机刷新令牌；刷新令牌哈希后写入原来的 `user_token` 表。
2. **鉴权依赖** `get_current_user`：不再“拿 token 查 `user_token` 表”，而是“验签 JWT → 取 `sub` → 按用户 ID 查 `user` 表”。
3. **前端**：请求头改成标准的 `Authorization: Bearer <accessToken>`；访问令牌 401 时自动调用 `/api/user/refresh` 换新令牌并重试原请求。

数据库**不需要改表结构**：继续复用 `user_token` 表，只是 `token` 字段的含义从“UUID 明文”变成“刷新令牌的 SHA-256 哈希”。旧 UUID 记录会自然失效，建议登录一次或执行 `DELETE FROM user_token;` 清空。

改动文件清单：

| 端 | 文件 | 操作 |
| --- | --- | --- |
| 后端 | `requirements.txt` | 增加 `PyJWT` |
| 后端 | `toutiao_backend/.env` | 增加 JWT 配置 |
| 后端 | `toutiao_backend/config/jwt_config.py` | 新建 |
| 后端 | `toutiao_backend/utils/jwt_utils.py` | 新建 |
| 后端 | `toutiao_backend/models/users.py` | 只改注释（可选） |
| 后端 | `toutiao_backend/schemas/users.py` | 改响应/请求模型 |
| 后端 | `toutiao_backend/crud/users.py` | 重写令牌相关函数 |
| 后端 | `toutiao_backend/utils/auth.py` | 重写鉴权依赖 |
| 后端 | `toutiao_backend/routers/users.py` | 登录/注册/刷新/登出接口 |
| 后端 | `README.md` | 更新认证说明 |
| 前端 | `toutiao_frontend/src/store/user.js` | 保存双令牌、刷新、登出 |
| 前端 | `toutiao_frontend/src/utils/http.js` | 新建 axios 实例 + `authFetch` |
| 前端 | `toutiao_frontend/src/store/modules/favorite.js` | 改用统一 http 实例 |
| 前端 | `toutiao_frontend/src/store/modules/history.js` | 改用统一 http 实例 |
| 前端 | `toutiao_frontend/src/views/AIChat.vue` | SSE 请求改用 `authFetch` |
| 前端 | `toutiao_frontend/src/views/Profile.vue` | 修 `userId` 显示、改密后重新登录 |

建议执行顺序：**先备份 → 装依赖/配密钥 → 后端 6 个文件 → 用 Swagger 自测 → 再改前端 → 联调**。不要前后端一起改完再运行，否则出错时很难定位。

---

## 1. 当前项目的认证是怎么工作的

先把现状看清楚，后面的改动才有依据。

### 1.1 后端代码走读

**（1）数据模型：`toutiao_backend/models/users.py`**

```python
class UserToken(Base):
    __tablename__ = "user_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
```

一个用户可以有多行记录，但当前业务逻辑实际上按“一个用户一个 token”来用。

**（2）生成令牌：`toutiao_backend/crud/users.py`**

```python
async def create_user_token(db: AsyncSession, user_id: int):
    token = str(uuid.uuid4())                       # 36 位随机 UUID
    expires_at = datetime.now() + timedelta(days=7) # 固定 7 天

    query = select(UserToken).where(UserToken.user_id == user_id)
    result = await db.execute(query)
    user_token = result.scalar_one_or_none()

    if user_token:
        user_token.token = token                    # 覆盖旧 token
        user_token.expires_at = expires_at
    else:
        user_token = UserToken(user_id=user_id, token=token, expires_at=expires_at)
        db.add(user_token)
        await db.commit()
        await db.refresh(user_token)

    return token
```

注意：`if user_token` 分支没有显式 `commit()`，目前是靠 `get_db()` 在请求结束时统一提交才“碰巧”生效。改造时建议显式提交，避免以后换数据库会话管理方式时踩坑。

**（3）校验令牌：`toutiao_backend/utils/auth.py`**

```python
async def get_current_user(
        authorization: str = Header(..., alias="Authorization"),
        db: AsyncSession = Depends(get_db)
):
    token = authorization.replace("Bearer ", "")   # 简单字符串替换
    user = await users.get_user_token(db, token)   # 查 user_token 表
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user
```

**（4）查询令牌：`toutiao_backend/crud/users.py`**

```python
async def get_user_token(db: AsyncSession, token: str):
    query = select(UserToken).where(UserToken.token == token)
    result = await db.execute(query)
    db_token = result.scalar_one_or_none()
    if not db_token or db_token.expires_at < datetime.now():
        return None

    query = select(User).where(User.id == db_token.user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()
```

**（5）登录/注册：`toutiao_backend/routers/users.py`**

```python
@router.post("/register")
async def registers(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    ...
    user = await users.create_users(db, user_data)
    token = await users.create_user_token(db, user.id)
    response_data = UserAuthResponse(token=token, user_info=...)
    return success_response(...)

@router.post("/login")
async def login(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    user = await users.authenticate_user(db, user_data.username, user_data.password)
    token = await users.create_user_token(db, user.id)
    response_data = UserAuthResponse(token=token, user_info=...)
    return success_response(...)
```

### 1.2 前端代码走读

- `src/store/user.js`：登录成功后把 `data.token` 存进 Pinia 的 `token` 字段，并持久化到 localStorage。
- `src/config/api.js`：后端地址 `http://127.0.0.1:8000`。
- 所有需要登录的请求都手动加请求头，但格式是**裸 token**：

```js
headers: {
  Authorization: userStore.token   // 实际发出去是 "Authorization: 550e8400-e29b-..."
}
```

- `src/views/AIChat.vue` 里 3 个 `fetch` 调用（聊天 SSE、历史列表、清空历史）也是手动加裸 token。
- `src/router/index.js` 的路由守卫只判断 `userStore.token` 是否存在。
- `src/views/Profile.vue` 用 `userStore.token.substring(0, 5)` 当作“账号 ID”显示。

### 1.3 现有实现的问题（为什么值得升级）

| 问题 | 具体表现 | 影响 |
| --- | --- | --- |
| 每次请求查两次库 | 先查 `user_token`，再查 `user` | 请求量上来后数据库压力翻倍 |
| 令牌明文入库 | `user_token.token` 就是可用凭证 | 数据库一旦泄露，所有登录态直接被盗 |
| 服务端有状态 | 每台后端都必须连同一个库才能校验 | 横向扩容、拆微服务不方便 |
| 令牌无标准 | 自定义 36 位字符串，没有签名、没有 claims | 无法跨服务信任，无法携带角色/过期信息 |
| 有效期固定 7 天 | 没有“短期访问 + 长期刷新”的分层 | 令牌一旦泄露，7 天内都有效 |
| 登出是“假登出” | 前端只清本地状态，后端 token 仍在 | 旧 token 在 7 天内仍可继续用（直到下次登录覆盖） |
| 改密不失效旧令牌 | 改完密码，旧 token 还能用 | 账号被盗后改密无法把攻击者踢下线 |
| 请求头不标准 | `Authorization: <token>` 而不是 `Bearer <token>` | 不符合 RFC 6750，Swagger/网关/第三方工具不认 |
| 前端拿 token 前 5 位当 ID | `token.substring(0, 5)` | 改造后会显示成 `eyJhb`，是错误信息 |

> 说明：UUID 随机令牌本身并不“低级”，它其实就是一种**服务端 Session Token**。它的优点是撤销简单；缺点是每次都要查库、明文存储、无标准。JWT 不是无条件更好，而是换了另一组权衡。第 3 章会讲清楚。

### 1.4 改造后的目标

- 访问令牌是标准 JWT，服务端只验签 + 查一次用户表。
- 访问令牌短期有效（默认 30 分钟），泄露窗口小。
- 刷新令牌长期有效（默认 7 天），数据库只存哈希，可撤销。
- 登出、改密可以让刷新令牌立即失效。
- 前端统一 `Bearer` 请求头，401 时自动刷新并重试。
- 不改数据库表结构，降低迁移风险。

---

## 2. JWT 原理（新手向）

### 2.1 一句话理解

JWT（JSON Web Token，RFC 7519）是一段**带签名的、自包含的字符串**。服务端不需要查库，只要用密钥验签，就能判断“这段内容是不是我签发的、有没有被改过、有没有过期”。

JWT 长这样，由两个点分成三段：

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcm5hbWUiOiJhZG1pbiIsImV4cCI6MTczMDAwMTgwMH0.5m9p8Q...
└──────────── header ────────────┘ └──────────────── payload ────────────────┘ └──── signature ────┘
```

### 2.2 三段分别是什么

**Header（头部）**：说明用什么算法签名。

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

**Payload（负载）**：真正要传递的数据，也叫 claims（声明）。

```json
{
  "sub": "1",
  "username": "admin",
  "type": "access",
  "jti": "8f14e45fceea167a5a36dedd4bea2543",
  "iss": "toutiao-api",
  "iat": 1730000000,
  "exp": 1730001800
}
```

常用标准字段：

| 字段 | 全称 | 含义 | 本方案用途 |
| --- | --- | --- | --- |
| `sub` | subject | 主体，通常是用户 ID | 存用户 ID（字符串） |
| `iss` | issuer | 签发者 | 固定 `toutiao-api` |
| `iat` | issued at | 签发时间（Unix 秒） | 记录签发时间 |
| `exp` | expiration time | 过期时间（Unix 秒） | 30 分钟后过期 |
| `jti` | JWT ID | 令牌唯一 ID | 将来做黑名单/审计 |
| `type` | 自定义 | 令牌类型 | 防止刷新令牌被当访问令牌用 |

**Signature（签名）**：用密钥对前两段做 HMAC-SHA256。

```
signature = HMAC-SHA256(
    base64url(header) + "." + base64url(payload),
    JWT_SECRET_KEY
)
```

三段分别做 **Base64URL 编码**（不是加密），然后用 `.` 拼起来。

### 2.3 签发与验签的过程

**签发（登录成功时，服务端做）**：

1. 写 header 和 payload。
2. 把 header、payload 分别 Base64URL 编码，用 `.` 拼成 `signing_input`。
3. 用密钥对 `signing_input` 做 HMAC-SHA256，得到签名。
4. 把签名也 Base64URL 编码，拼成 `header.payload.signature`，返回给前端。

**验签（每次请求，服务端做）**：

1. 按 `.` 拆成三段。
2. 重新计算 `HMAC-SHA256(header + "." + payload, 密钥)`。
3. 和第三段签名比对。不一致 → 令牌被篡改或不是本服务签发 → 401。
4. 校验 `exp` 是否过期、`iss` 是否匹配、`type` 是否等于 `access`。
5. 取出 `sub`（用户 ID），查一次 `user` 表，确认用户仍存在。
6. 通过，返回 `User` 对象给路由函数。

> 关键点：**签名只能防篡改，不能防偷看**。Payload 只是 Base64URL，任何人拿到 token 都能解码看到内容。所以**绝对不要把密码、手机号、身份证等敏感信息放进 JWT**。

### 2.4 为什么需要两个令牌

如果只发一个 JWT，会陷入两难：

- 有效期长（比如 7 天）：用户不用频繁登录，但令牌泄露后 7 天都能用，且服务端很难撤销。
- 有效期短（比如 10 分钟）：泄露风险小，但用户每 10 分钟就要重新登录，体验差。

双令牌就是折中：

- **Access Token**：短命（30 分钟），每次业务请求都带。JWT 自包含，服务端验签即可，不查令牌表。
- **Refresh Token**：长命（7 天），只在“换新访问令牌”时用一次。它是随机字符串，数据库存哈希，所以可以撤销、可以轮换。

这样既保留了 JWT 的“无状态校验”，又通过刷新令牌把“撤销”能力补回来。

### 2.5 JWT 不是什么

- 不是加密：Payload 可读。
- 不是 Session 的完全替代：JWT 的痛点是“到期前难以撤销”，所以本方案才配了数据库里的刷新令牌。
- 不是“用了就安全”：密钥泄露、XSS 偷 localStorage、HTTP 明文传输，都会让 JWT 失效。
- 不是只能 HS256：还有 RS256/ES256（非对称），适合多服务共享公钥的场景。本项目单体应用用 HS256 足够。

---

## 3. 使用 JWT 的优势与代价

### 3.1 对本项目的具体收益

| 收益 | 说明 |
| --- | --- |
| 少一次数据库查询 | 旧方案每次请求查 `user_token` + `user`；新方案只验签 + 查 `user` |
| 令牌不再明文入库 | 访问令牌根本不入库；刷新令牌只存 SHA-256 哈希，库泄露也不能直接登录 |
| 短有效期 | 访问令牌默认 30 分钟，比原来的 7 天大幅缩小泄露窗口 |
| 标准协议 | `Authorization: Bearer <token>`，Swagger、Nginx、API 网关、Postman 都认 |
| 可携带声明 | 用户 ID、用户名、角色、租户等可以放进 claims，减少查库 |
| 易扩展 | 以后拆服务，只要共享密钥（HS256）或公钥（RS256），不用共享 session 表 |
| 前端体验好 | 访问令牌过期后自动刷新，用户无感知 |
| 可撤销 | 刷新令牌存库，登出/改密时删除即可；访问令牌靠短有效期兜底 |

### 3.2 代价与风险（一定要知道）

| 代价 | 说明 | 本方案的应对 |
| --- | --- | --- |
| 访问令牌到期前无法“立刻”撤销 | 删了刷新令牌，已签发的访问令牌在 30 分钟内仍有效 | 短有效期 + 可选 `token_version` / Redis 黑名单 |
| 令牌体积更大 | JWT 通常 200～400 字符，UUID 只有 36 字符 | 只放必要 claims，别塞大对象 |
| Payload 可读 | 不能放敏感信息 | 只放用户 ID、用户名、类型、jti |
| 密钥管理 | 密钥泄露 = 所有人可伪造令牌 | 放 `.env`，至少 32 字符，生产用密钥管理服务 |
| 前端存储风险 | localStorage 可被 XSS 读取 | 生产建议 httpOnly Cookie + CSRF 防护；教学项目可用 localStorage |
| 时钟偏差 | 服务器时间不准会导致“刚签发就过期” | 验签加 10 秒 leeway；服务器开 NTP |
| 算法混淆攻击 | 攻击者把 `alg` 改成 `none` 或 RS256/HS256 混淆 | 验签时固定 `algorithms=["HS256"]`，永远不信任 header 里的 alg |

### 3.3 与当前 UUID 方案的对比

| 维度 | 当前 UUID Token | JWT Access Token |
| --- | --- | --- |
| 服务端存储 | 必须存明文 | 不存（刷新令牌另存哈希） |
| 校验方式 | 查表比对字符串 | 验签 + 校验 claims |
| 每次请求 DB 查询 | 2 次（token + user） | 1 次（user） |
| 撤销 | 删行立即失效 | 到期前难撤销，需黑名单/版本号 |
| 横向扩展 | 依赖共享数据库 | 依赖共享密钥，无状态 |
| 标准 | 自定义 | RFC 7519 / RFC 6750 |
| 泄露后风险 | 数据库泄露即全部失守 | 密钥泄露才可伪造；令牌泄露受短有效期限制 |
| 适用场景 | 单体、需要强撤销、请求量小 | 单体/微服务、请求量大、可接受短窗口 |

### 3.4 什么时候不该用 JWT

- 需要“管理员一键踢下线，立即生效”且不能等 30 分钟：要加黑名单或版本号，或者干脆用 Session。
- 前端跑在不可信环境、又必须把令牌放 localStorage：XSS 风险高。
- 团队没有能力管理密钥、HTTPS、时钟同步：JWT 会放大运维问题。

对本项目来说，JWT 是合适的：单体 FastAPI + Vue，已经有用户表，改造量可控，正好用来学习标准认证。

---

## 4. 改造总体设计

### 4.1 架构图

```
┌─────────────┐        1. POST /api/user/login            ┌──────────────────┐
│   Vue 前端   │ ─────────────────────────────────────────> │   FastAPI 后端    │
│             │                                            │                  │
│             │ <───────────────────────────────────────── │ 生成 access JWT  │
│             │   2. accessToken + refreshToken + userInfo  │ 生成 refresh 随机串│
│             │                                            │ refresh 存 SHA256 │
│             │                                            └──────────────────┘
│             │
│             │   3. GET /api/user/info
│             │      Authorization: Bearer <accessToken>
│             │ ─────────────────────────────────────────> ┌──────────────────┐
│             │                                            │ 验签 + 校验 exp   │
│             │ <───────────────────────────────────────── │ 查 user 表        │
│             │              4. 用户信息                    └──────────────────┘
│             │
│             │   5. access 过期，收到 401
│             │   6. POST /api/user/refresh { refreshToken }
│             │ ─────────────────────────────────────────> ┌──────────────────┐
│             │                                            │ 查 refresh 哈希   │
│             │ <───────────────────────────────────────── │ 校验过期          │
│             │   7. 新 accessToken                         │ 签发新 access     │
│             │                                            └──────────────────┘
│             │   8. 用新 accessToken 重试原请求
└─────────────┘
```

### 4.2 Token 设计

| 项目 | Access Token | Refresh Token |
| --- | --- | --- |
| 格式 | JWT（三段） | `secrets.token_urlsafe(48)` 随机串 |
| 算法 | HS256 | 无（不透明字符串） |
| 有效期 | 30 分钟（可配） | 7 天（可配） |
| 存哪里 | 前端 localStorage + Pinia | 前端 localStorage + Pinia |
| 服务端存哪里 | 不存 | `user_token.token` 存 SHA-256 哈希 |
| 每次请求 | 放 `Authorization: Bearer` | 只在 `/refresh`、`/logout` 的请求体里 |
| 能否撤销 | 到期前不能（除非加黑名单/版本号） | 删除数据库行即可 |
| 主要 claims | `sub`、`username`、`type=access`、`jti`、`iss`、`iat`、`exp` | 无 claims（随机串） |

为什么刷新令牌不用 JWT？

- 它只在刷新接口用一次，不需要“自包含”带来的性能优势。
- 随机串熵更高，且必须查库才能撤销；用 JWT 反而还要额外存 `jti` 做撤销。
- 数据库只存哈希，泄露后无法直接使用。

### 4.3 接口变化

| 接口 | 改造前 | 改造后 |
| --- | --- | --- |
| `POST /api/user/register` | 返回 `{ token, userInfo }` | 返回 `{ accessToken, refreshToken, tokenType, expiresIn, userInfo }` |
| `POST /api/user/login` | 返回 `{ token, userInfo }` | 同上 |
| `POST /api/user/refresh` | 不存在 | 新增，请求体 `{ refreshToken }`，返回 `{ accessToken, tokenType, expiresIn }` |
| `POST /api/user/logout` | 不存在 | 新增，请求体 `{ refreshToken }`，删除服务端刷新令牌 |
| `GET /api/user/info` | `Authorization: <token>` | `Authorization: Bearer <accessToken>` |
| 其他需登录接口 | 同上 | 同上 |

> 字段名用 `accessToken` / `refreshToken`（camelCase），和前端现有 `userInfo` 风格一致。Pydantic 内部字段用 snake_case，通过 `alias` 输出 camelCase。

### 4.4 数据库设计

**不新增表、不改字段**，继续用 `user_token`：

```sql
-- 改造前：token 存 UUID 明文
-- 改造后：token 存刷新令牌的 SHA-256 十六进制（64 个字符）
SELECT id, user_id, token, expires_at, created_at FROM user_token;
```

| 字段 | 改造后含义 |
| --- | --- |
| `id` | 自增主键 |
| `user_id` | 用户 ID |
| `token` | `sha256(refreshToken)`，64 位十六进制 |
| `expires_at` | 刷新令牌过期时间（7 天后） |
| `created_at` | 创建时间 |

当前业务是“一个用户一个会话”，所以登录时会先删除该用户旧的 `user_token` 行，再插入新行。这样第二次登录会让旧设备的刷新令牌立即失效（旧设备的访问令牌仍可用到 30 分钟过期）。

如果你以后要支持“多设备同时在线”，把 `issue_refresh_token` 里的 `DELETE` 去掉，改成每次插入新行即可；查询按 token 哈希查，天然支持多行。

### 4.5 兼容与迁移策略

- **旧 UUID 令牌**：新代码只认 JWT，旧 token 会 401。上线后让所有用户重新登录一次即可，或用 `DELETE FROM user_token;` 清空。
- **前端过渡**：后端 `get_current_user` 同时兼容 `Bearer <jwt>` 和裸 `<jwt>`，这样前端可以晚一点改；但正式版建议只保留 `Bearer`。
- **字段过渡**：前端解析登录响应时兼容 `accessToken || token`，方便你分步改。
- **数据库**：无需 DDL，回滚也简单。

---

## 5. 动手前的准备

### 5.1 备份与分支

先确保改坏了能回来：

```powershell
cd D:\vscodeproject\HelloFastAPI

# 如果你用 git（当前目录有 .git），先提交或建分支
git status
git add -A
git commit -m "chore: 备份 JWT 改造前代码"
git switch -c feature/jwt-auth
```

如果 git 提示 `dubious ownership`（当前机器出现过），先执行一次：

```powershell
git config --global --add safe.directory D:/vscodeproject/HelloFastAPI
```

不想用 git 也可以手动复制整个项目目录做备份。

### 5.2 安装 PyJWT

项目根目录有 `.venv`，确认你平时启动后端用的是它：

```powershell
cd D:\vscodeproject\HelloFastAPI
.\.venv\Scripts\python.exe -m pip install "PyJWT==2.10.1"
.\.venv\Scripts\python.exe -c "import jwt; print(jwt.__version__)"
```

如果安装失败或版本不存在，用：

```powershell
.\.venv\Scripts\python.exe -m pip install "PyJWT>=2.8,<3.0"
```

然后把依赖写进 `requirements.txt`（建议锁版本，和项目里其他依赖风格一致）：

```text
PyJWT==2.10.1
```

> 不要用 `python-jose` 替代，除非你明确需要它。FastAPI 官方文档和社区最常用的是 PyJWT，API 简单，纯 Python，Windows 安装无编译问题。

### 5.3 生成密钥并写入 `.env`

生成一个 64 位十六进制随机密钥：

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

复制输出，编辑 `toutiao_backend/.env`，在文件末尾追加（把 `替换成...` 换成你刚生成的值）：

```env
# ===== JWT =====
JWT_SECRET_KEY=替换成你生成的64位十六进制字符串
JWT_ALGORITHM=HS256
JWT_ISSUER=toutiao-api
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
```

注意：

- `.env` 已在 `.gitignore` 里，不要提交。
- 等号两边不要留空格（虽然 dotenv 能处理，但避免踩坑）。
- 密钥至少 32 个字符；建议 64 位十六进制（64 个字符）。
- 换密钥会让所有已签发 JWT 失效，这是正常的“全站下线”操作。
- 生产环境不要把密钥写进镜像，用环境变量注入（Docker `-e` / K8s Secret）。
- 特别注意：当前 `Dockerfile` 用的是 `COPY toutiao_backend/ ./toutiao_backend/`，如果 `toutiao_backend/.env` 存在，会被一起打进镜像。生产部署建议加 `.dockerignore` 排除 `.env`，或者只在运行时通过环境变量注入 JWT 配置。

### 5.4 目录与文件确认

改造前先确认这些文件存在（都在 `toutiao_backend` 下）：

```text
toutiao_backend/
├── config/
│   ├── db_config.py
│   └── jwt_config.py        ← 新建
├── models/users.py
├── schemas/users.py
├── crud/users.py
├── routers/users.py
├── utils/
│   ├── auth.py
│   ├── security.py
│   └── jwt_utils.py         ← 新建
├── main.py
└── .env
```

前端：

```text
toutiao_frontend/src/
├── store/user.js
├── store/modules/favorite.js
├── store/modules/history.js
├── views/AIChat.vue
├── views/Profile.vue
├── router/index.js
├── config/api.js
└── utils/http.js            ← 新建（utils 目录不存在就新建）
```

### 5.5 启动方式（后面自测会反复用）

```powershell
cd D:\vscodeproject\HelloFastAPI\toutiao_backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

前端另开一个终端：

```powershell
cd D:\vscodeproject\HelloFastAPI\toutiao_frontend
npm run dev
```

> `.env` 改了之后，`--reload` 不一定会重新加载环境变量，**手动重启后端**最稳。

---

## 6. 后端改造（逐步）

### Step 1：新建 `toutiao_backend/config/jwt_config.py`

```python
"""JWT 相关配置，从 toutiao_backend/.env 读取。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# config/jwt_config.py -> config -> toutiao_backend
BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=BACKEND_ROOT / ".env", override=False)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是整数，当前值为：{raw}") from exc


JWT_SECRET_KEY = (os.getenv("JWT_SECRET_KEY") or "").strip()
JWT_ALGORITHM = (os.getenv("JWT_ALGORITHM") or "HS256").strip()
JWT_ISSUER = (os.getenv("JWT_ISSUER") or "toutiao-api").strip()
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = _get_int("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30)
JWT_REFRESH_TOKEN_EXPIRE_DAYS = _get_int("JWT_REFRESH_TOKEN_EXPIRE_DAYS", 7)

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "未配置 JWT_SECRET_KEY：请在 toutiao_backend/.env 中添加一行 "
        "JWT_SECRET_KEY=<随机字符串>"
    )
if len(JWT_SECRET_KEY) < 32:
    raise RuntimeError("JWT_SECRET_KEY 至少需要 32 个字符，建议使用 64 位十六进制")
if JWT_ALGORITHM != "HS256":
    raise RuntimeError("当前示例仅支持 HS256，请勿随意修改 JWT_ALGORITHM")
if JWT_ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
    raise RuntimeError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES 必须大于 0")
if JWT_REFRESH_TOKEN_EXPIRE_DAYS <= 0:
    raise RuntimeError("JWT_REFRESH_TOKEN_EXPIRE_DAYS 必须大于 0")
```

设计说明：

- 用绝对路径加载 `.env`，不管从哪个目录启动都能找到。
- `override=False`：系统环境变量优先，方便 Docker/CI 注入。
- 启动时校验，配置缺失直接报错，避免“运行到登录才 500”。

### Step 2：新建 `toutiao_backend/utils/jwt_utils.py`

```python
"""JWT 访问令牌的生成/解析，以及刷新令牌的生成/哈希。"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError  # noqa: F401

from config.jwt_config import (
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    JWT_SECRET_KEY,
)


def create_access_token(user_id: int, username: str) -> tuple[str, int]:
    """生成访问令牌，返回 (token, 有效期秒数)。"""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),          # JWT 规范要求 sub 是字符串
        "username": username,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": expires_at,
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60


def create_refresh_token() -> tuple[str, datetime]:
    """生成刷新令牌，返回 (明文, 过期时间)。

    明文只返回给客户端；数据库只保存它的 SHA-256 哈希。
    过期时间用本地 naive datetime，和 MySQL DATETIME 的比较方式保持一致。
    """
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    return token, expires_at


def hash_refresh_token(token: str) -> str:
    """刷新令牌是高熵随机串，用 SHA-256 足够，不需要 bcrypt。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> dict[str, Any]:
    """解析并校验访问令牌；失败时抛 PyJWT 的异常。"""
    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],   # 固定算法，防止 alg 混淆攻击
        issuer=JWT_ISSUER,
        options={"require": ["exp", "iat", "iss", "sub", "type"]},
        leeway=10,                    # 容忍 10 秒时钟偏差
    )
```

设计说明：

- `sub` 用字符串：JWT 规范如此，PyJWT 新版本也会校验。
- 访问令牌时间用 **UTC aware datetime**；刷新令牌过期时间用 **本地 naive datetime**，因为要和 MySQL 的 `DATETIME` 直接比较。两者不要混用。
- `leeway=10` 避免服务器之间几秒钟时钟偏差导致“刚签发就过期”。
- `algorithms=[...]` 必须显式传，且只允许 HS256。
- `options={"require": [...]}` 强制这些 claim 必须存在，少了就算无效。

### Step 3：修改 `toutiao_backend/models/users.py`（只改注释）

把 `UserToken.token` 的注释改准确即可，表结构不动：

```python
class UserToken(Base):
    __tablename__ = "user_token"

    __table_args__ = (
        Index('token_UNIQUE', 'token'),
        Index('fk_user_token_user_idx', 'user_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="Token ID")
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False, comment="用户ID")
    # 改造后这里存的是刷新令牌的 SHA-256 哈希，不再是 UUID 明文
    token: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, comment="刷新令牌哈希")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="过期时间")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        comment="创建时间"
    )
```

> `String(200)` 足够放 64 位十六进制哈希。访问令牌（JWT）不存这里，所以不用担心 JWT 太长。

### Step 4：修改 `toutiao_backend/schemas/users.py`

完整替换为：

```python
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UserRequest(BaseModel):
    username: str
    password: str


class UserInfoBase(BaseModel):
    nickname: Optional[str] = Field(None, max_length=100, description="用户昵称")
    avatar: Optional[str] = Field(None, max_length=200, description="用户头像")
    gender: Optional[str] = Field(None, max_length=10, description="用户性别")
    bio: Optional[str] = Field(None, max_length=200, description="用户简介")


class UserInfoResponse(UserInfoBase):
    id: int
    username: str

    model_config = ConfigDict(from_attributes=True)


class UserAuthResponse(BaseModel):
    """登录/注册成功后的响应。"""

    access_token: str = Field(..., alias="accessToken", description="访问令牌（JWT）")
    refresh_token: str = Field(..., alias="refreshToken", description="刷新令牌，仅返回一次")
    token_type: str = Field("bearer", alias="tokenType", description="令牌类型")
    expires_in: int = Field(..., alias="expiresIn", description="访问令牌有效期（秒）")
    user_info: UserInfoResponse = Field(..., alias="userInfo")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class RefreshTokenRequest(BaseModel):
    """刷新/登出接口的请求体。"""

    refresh_token: str = Field(..., min_length=10, alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)


class TokenRefreshResponse(BaseModel):
    """刷新成功后的响应。"""

    access_token: str = Field(..., alias="accessToken")
    token_type: str = Field("bearer", alias="tokenType")
    expires_in: int = Field(..., alias="expiresIn")

    model_config = ConfigDict(populate_by_name=True)


class UserChangePasswordRequest(BaseModel):
    old_password: str = Field(..., alias="oldPassword", description="旧密码")
    # 顺手修复：原来 max_length=6 会把 7 位以上的新密码全部判为非法
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=72,
        alias="newPassword",
        description="新密码",
    )
```

为什么用 `alias`？

- Python 内部习惯 snake_case；前端现有字段是 camelCase（`userInfo`、`oldPassword`）。
- `alias` 负责“内部 snake_case，对外 camelCase”。
- `populate_by_name=True` 让你用 snake_case 构造模型也能成功（后端代码里会这样用）。
- 项目里的 `success_response` 用 `jsonable_encoder`，它默认 `by_alias=True`，所以最终 JSON 是 `accessToken`。

### Step 5：修改 `toutiao_backend/crud/users.py`

完整替换为：

```python
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.users import UserInfoBase, UserRequest
from models.users import User, UserToken
from utils import security
from utils.jwt_utils import create_refresh_token, hash_refresh_token


# 根据用户名查询数据库
async def get_user_by_username(db: AsyncSession, username: str):
    query = select(User).where(User.username == username)
    result = await db.execute(query)
    return result.scalar_one_or_none()


# 创建用户
async def create_users(db: AsyncSession, user_data: UserRequest):
    hashed_psw = security.hash_password(user_data.password)
    user = User(username=user_data.username, password=hashed_psw)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def issue_refresh_token(db: AsyncSession, user_id: int) -> str:
    """为用户签发刷新令牌，返回明文；数据库只存哈希。

    单会话策略：登录时删掉该用户旧的刷新令牌，旧设备需要重新登录。
    如果以后要多设备同时在线，把 DELETE 去掉，改为每次 INSERT 即可。
    """
    raw_token, expires_at = create_refresh_token()
    token_hash = hash_refresh_token(raw_token)

    await db.execute(delete(UserToken).where(UserToken.user_id == user_id))
    db.add(
        UserToken(
            user_id=user_id,
            token=token_hash,
            expires_at=expires_at,
        )
    )
    await db.commit()
    return raw_token


async def get_user_by_refresh_token(db: AsyncSession, raw_token: str) -> User | None:
    """用明文刷新令牌换用户；无效或过期返回 None。"""
    token_hash = hash_refresh_token(raw_token)
    query = select(UserToken).where(UserToken.token == token_hash)
    result = await db.execute(query)
    row = result.scalar_one_or_none()

    if row is None:
        return None

    if row.expires_at <= datetime.now():
        # 过期行顺手清理，避免表里堆积垃圾
        await db.delete(row)
        await db.commit()
        return None

    return await db.get(User, row.user_id)


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> bool:
    """删除指定的刷新令牌（登出）。返回是否真的删到了。"""
    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(delete(UserToken).where(UserToken.token == token_hash))
    await db.commit()
    return (result.rowcount or 0) > 0


async def revoke_all_refresh_tokens(db: AsyncSession, user_id: int) -> None:
    """撤销该用户所有刷新令牌（改密、强制下线）。"""
    await db.execute(delete(UserToken).where(UserToken.user_id == user_id))
    await db.commit()


async def authenticate_user(db: AsyncSession, username: str, password: str):
    user = await get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not security.verify_password(password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user


async def update_user_info(db: AsyncSession, username: str, user_data: UserInfoBase):
    query = update(User).where(User.username == username).values(
        **user_data.model_dump(exclude_unset=True, exclude_none=True)
    )
    result = await db.execute(query)
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")

    updated_user = await get_user_by_username(db, username)
    return updated_user


async def change_password(db: AsyncSession, user: User, old_password: str, new_password: str):
    if not security.verify_password(old_password, user.password):
        return False

    hashed_new_pwd = security.hash_password(new_password)
    user.password = hashed_new_pwd
    db.add(user)

    # 改密后撤销所有刷新令牌：旧设备不能再续期，必须重新登录
    await db.execute(delete(UserToken).where(UserToken.user_id == user.id))
    await db.commit()
    await db.refresh(user)
    return True
```

说明：

- 删掉了 `get_user_token`，`utils/auth.py` 不再调用它。
- 删掉了 `uuid` 和 `timedelta` 的导入（不再需要）。
- 所有写操作都显式 `commit()`，不再依赖 `get_db()` 的兜底提交。
- `get_user_by_refresh_token` 用哈希查，数据库里没有明文。

### Step 6：修改 `toutiao_backend/utils/auth.py`

完整替换为：

```python
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_config import get_db
from models.users import User
from utils.jwt_utils import decode_access_token

# auto_error=False：没有 Authorization 头时返回 None，由我们自己抛 401
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization 头中解析 JWT，返回当前用户。

    优先使用 HTTPBearer 解析出的 credentials；如果没有，再兼容旧格式
    `Authorization: <token>`（不带 Bearer 前缀），方便前端分步改造。
    """
    token = credentials.credentials if credentials else None

    if not token and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            token = value.strip()
        else:
            token = authorization.strip()

    if not token:
        raise _unauthorized("缺少身份凭证，请先登录")

    try:
        payload = decode_access_token(token)
    except ExpiredSignatureError:
        raise _unauthorized("登录已过期，请重新登录")
    except InvalidTokenError:
        raise _unauthorized("身份凭证无效")

    if payload.get("type") != "access":
        raise _unauthorized("身份凭证类型错误")

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _unauthorized("身份凭证内容无效")

    user = await db.get(User, user_id)
    if user is None:
        raise _unauthorized("用户不存在或已被删除")

    return user
```

关键点：

- `HTTPBearer` 让 Swagger 文档出现右上角 `Authorize` 按钮，方便测试。
- `auto_error=False` 让我们统一返回“中文 + 401”，而不是 FastAPI 默认的 403。
- 显式捕获 `ExpiredSignatureError`（过期）和 `InvalidTokenError`（签名错、格式错、claim 缺失等），给前端不同提示。
- `payload["sub"]` 转 int；转换失败说明 token 被伪造或格式不对。
- `db.get(User, user_id)` 只查一次用户表；比旧方案少一次 `user_token` 查询。
- 兼容裸 token 只是过渡，稳定后可以删掉 `authorization` 参数和 fallback 分支。

### Step 7：修改 `toutiao_backend/routers/users.py`

完整替换为：

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_config import get_db
from crud import users
from models.users import User
from schemas.users import (
    RefreshTokenRequest,
    TokenRefreshResponse,
    UserAuthResponse,
    UserChangePasswordRequest,
    UserInfoBase,
    UserInfoResponse,
    UserRequest,
)
from utils.auth import get_current_user
from utils.jwt_utils import create_access_token
from utils.response import success_response

router = APIRouter(prefix="/api/user", tags=["users"])


def build_auth_response(user: User, refresh_token: str) -> UserAuthResponse:
    """把 User + 刷新令牌组装成登录响应。"""
    access_token, expires_in = create_access_token(user.id, user.username)
    return UserAuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user_info=UserInfoResponse.model_validate(user),
    )


@router.post("/register")
async def registers(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    # 注册逻辑：验证用户是否存在 ——》 创建用户 ——》 签发双令牌 ——》 响应结果
    existing_user = await users.get_user_by_username(db, user_data.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    user = await users.create_users(db, user_data)
    refresh_token = await users.issue_refresh_token(db, user.id)
    response_data = build_auth_response(user, refresh_token)
    return success_response(message="User registered successfully", data=response_data)


@router.post("/login")
async def login(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    user = await users.authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    refresh_token = await users.issue_refresh_token(db, user.id)
    response_data = build_auth_response(user, refresh_token)
    return success_response(message="User logged in successfully", data=response_data)


@router.post("/refresh")
async def refresh_token(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """用刷新令牌换新的访问令牌。"""
    user = await users.get_user_by_refresh_token(db, payload.refresh_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Refresh token 无效或已过期")

    access_token, expires_in = create_access_token(user.id, user.username)
    data = TokenRefreshResponse(access_token=access_token, expires_in=expires_in)
    return success_response(message="Token refreshed", data=data)


@router.post("/logout")
async def logout(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """登出：删除服务端刷新令牌。访问令牌会在到期后自然失效。"""
    await users.revoke_refresh_token(db, payload.refresh_token)
    return success_response(message="Logged out successfully")


@router.get("/info")
async def get_user_info(user: User = Depends(get_current_user)):
    return success_response(message="User info fetched successfully", data=UserInfoResponse.model_validate(user))


@router.put("/update")
async def update_user_info(
    user_data: UserInfoBase,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await users.update_user_info(db, user.username, user_data)
    return success_response(
        message="User updated successfully",
        data=UserInfoResponse.model_validate(updated),
    )


@router.put("/password")
async def change_password(
    password_data: UserChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    changed = await users.change_password(
        db, user, password_data.old_password, password_data.new_password
    )
    if not changed:
        raise HTTPException(status_code=400, detail="Invalid old password")
    return success_response(message="Password updated successfully, please login again")
```

说明：

- `/refresh` 不需要访问令牌，因为访问令牌已经过期了；它只要合法的刷新令牌。
- `/logout` 也不需要访问令牌，理由相同；有刷新令牌就足以删除会话。
- `/refresh` 不轮换刷新令牌：实现简单，7 天内有效。想更安全可以看第 10 章“刷新令牌轮换”。
- 改密后刷新令牌被删除；访问令牌最多还能用 30 分钟（见第 10 章如何让它立即失效）。

### Step 8：更新 `requirements.txt`

在文件里加一行（位置随意，建议按字母序放在 `PyMySQL` 附近）：

```text
PyJWT==2.10.1
```

### Step 9：清理旧令牌数据

旧 UUID 令牌已经无法通过 JWT 验签，保留着只会让用户“看起来登录了但一直 401”。建议清空：

```sql
USE news_app;
DELETE FROM `user_token`;
-- 可选：重置自增 ID
ALTER TABLE `user_token` AUTO_INCREMENT = 1;
```

> 不需要改表结构、不需要加字段。`user_token` 继续用，只是里面存的东西从 UUID 变成哈希。

### Step 10：启动后端并自测（先别改前端）

启动：

```powershell
cd D:\vscodeproject\HelloFastAPI\toutiao_backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

如果启动就报 `RuntimeError: 未配置 JWT_SECRET_KEY`，回到 5.3 检查 `.env` 路径和变量名，然后重启。

#### 测试 1：注册/登录返回双令牌

打开 `http://127.0.0.1:8000/docs`，调用 `POST /api/user/login`（没有账号就先注册）。预期响应：

```json
{
  "code": 200,
  "message": "User logged in successfully",
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIs...",
    "refreshToken": "3xJ...64位随机串...",
    "tokenType": "bearer",
    "expiresIn": 1800,
    "userInfo": {
      "id": 1,
      "username": "admin",
      "nickname": null,
      "avatar": null,
      "gender": "male",
      "bio": null
    }
  }
}
```

记下 `accessToken` 和 `refreshToken`。

#### 测试 2：用 Swagger 调受保护接口

1. 点右上角 `Authorize`。
2. 在 `HTTPBearer` 的输入框里粘贴 **accessToken**（只粘 token，不要自己加 `Bearer `，Swagger 会自动加）。
3. 调用 `GET /api/user/info`，预期 200。
4. 把 token 改错一个字符，再调用，预期 401。

#### 测试 3：PowerShell 命令行验证

```powershell
$body = @{ username = "admin"; password = "123456" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/user/login" `
  -ContentType "application/json" -Body $body

$access  = $login.data.accessToken
$refresh = $login.data.refreshToken

# 1) 正常访问
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8000/api/user/info" `
  -Headers @{ Authorization = "Bearer $access" }

# 2) 刷新访问令牌
$refreshBody = @{ refreshToken = $refresh } | ConvertTo-Json
$new = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/user/refresh" `
  -ContentType "application/json" -Body $refreshBody
$new.data.accessToken

# 3) 登出
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/user/logout" `
  -ContentType "application/json" -Body $refreshBody

# 4) 登出后再刷新，应该 401
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/user/refresh" `
  -ContentType "application/json" -Body $refreshBody `
  -SkipHttpErrorCheck
```

#### 测试 4：令牌过期与刷新

1. 把 `.env` 的 `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` 临时改成 `1`。
2. 重启后端。
3. 重新登录，等 70 秒（代码有 10 秒 leeway）。
4. `GET /api/user/info` → 预期 401，`message` 是“登录已过期，请重新登录”。
5. 用 `refreshToken` 调 `/api/user/refresh` → 200，拿到新 access。
6. 用新 access 调 `/api/user/info` → 200。
7. 测完把有效期改回 `30` 并重启。

#### 测试 5：改密后刷新令牌失效

1. 登录拿 refresh。
2. 调 `PUT /api/user/password`（需要 access），改密码。
3. 用旧 refresh 调 `/refresh` → 401。
4. 用新密码重新登录 → 200。

#### 测试 6：旧 UUID 令牌失效

拿改造前保存的旧 token 调 `/api/user/info` → 401。这说明新鉴权已经生效。

后端自测全部通过，再动前端。

---

## 7. 前端改造（逐步）

### Step 1：修改 `toutiao_frontend/src/store/user.js`

完整替换为：

```js
import { defineStore } from 'pinia';
import axios from 'axios';
import { apiConfig } from '../config/api';

export const useUserStore = defineStore('user', {
  state: () => ({
    userInfo: null,
    token: '',          // 访问令牌（JWT）。保留原名，页面里的 userStore.token 不用全改
    refreshToken: '',   // 刷新令牌
    isLogin: false,
    userBio: '这是我的个人简介'
  }),

  getters: {
    getUserInfo: (state) => state.userInfo,
    getToken: (state) => state.token,
    getLoginStatus: (state) => state.isLogin,
    getUserBio: (state) => state.userInfo?.bio || state.userBio
  },

  actions: {
    // 保存登录/注册响应里的双令牌和用户信息
    _applyAuthData(data) {
      if (!data) return;
      if (data.userInfo) {
        this.userInfo = data.userInfo;
      }
      this.token = data.accessToken || data.token || '';
      this.refreshToken = data.refreshToken || '';
      this.isLogin = Boolean(this.token);
    },

    // 清空本地登录态（不调后端）
    _clearAuth() {
      this.userInfo = null;
      this.token = '';
      this.refreshToken = '';
      this.isLogin = false;
    },

    async login(userData) {
      try {
        const response = await axios.post(`${apiConfig.baseURL}/api/user/login`, {
          username: userData.username,
          password: userData.password
        });

        if (response.data && response.data.code === 200) {
          this._applyAuthData(response.data.data);
          return { success: true, message: '登录成功' };
        }

        return {
          success: false,
          message: response.data?.message || '登录失败'
        };
      } catch (error) {
        console.error('登录请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '登录请求失败，请稍后再试'
        };
      }
    },

    async register(userData) {
      try {
        const response = await axios.post(`${apiConfig.baseURL}/api/user/register`, {
          username: userData.username,
          password: userData.password
        });

        if (response.data && response.data.code === 200) {
          this._applyAuthData(response.data.data);
          return { success: true, message: '注册成功' };
        }

        return {
          success: false,
          message: response.data?.message || '注册失败'
        };
      } catch (error) {
        console.error('注册请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '注册请求失败，请稍后再试'
        };
      }
    },

    // 登出：先清本地，再通知后端撤销刷新令牌（失败也不影响本地退出）
    async logout() {
      const refreshToken = this.refreshToken;
      this._clearAuth();

      if (!refreshToken) return;

      try {
        await axios.post(`${apiConfig.baseURL}/api/user/logout`, { refreshToken });
      } catch (error) {
        console.warn('登出接口调用失败（本地登录态已清除）:', error);
      }
    },

    // 用刷新令牌换新的访问令牌
    async refreshAccessToken() {
      if (!this.refreshToken) return false;

      try {
        const response = await axios.post(`${apiConfig.baseURL}/api/user/refresh`, {
          refreshToken: this.refreshToken
        });

        const data = response.data?.data;
        if (response.data?.code === 200 && data?.accessToken) {
          this.token = data.accessToken;
          this.isLogin = true;
          return true;
        }

        return false;
      } catch (error) {
        console.warn('刷新访问令牌失败:', error);
        // 只有明确 401 才清空；网络错误保留状态，允许用户重试
        if (error.response?.status === 401) {
          this._clearAuth();
        }
        return false;
      }
    },

    // 带 Bearer 头的 axios 请求；401 时自动刷新并重试一次
    async requestWithAuth(config) {
      const send = () => axios({
        ...config,
        headers: {
          ...(config.headers || {}),
          Authorization: `Bearer ${this.token}`
        }
      });

      try {
        return await send();
      } catch (error) {
        if (error.response?.status === 401) {
          const refreshed = await this.refreshAccessToken();
          if (refreshed) {
            return send();
          }
        }
        throw error;
      }
    },

    // 获取用户信息
    async getUserInfoDetail() {
      try {
        if (!this.token && !this.refreshToken) {
          return { success: false, message: '未登录' };
        }

        const response = await this.requestWithAuth({
          method: 'get',
          url: `${apiConfig.baseURL}/api/user/info`
        });

        if (response.data && response.data.code === 200) {
          this.userInfo = response.data.data;
          return {
            success: true,
            message: '获取用户信息成功',
            data: response.data.data
          };
        }

        return {
          success: false,
          message: response.data?.message || '获取用户信息失败'
        };
      } catch (error) {
        console.error('获取用户信息请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '获取用户信息请求失败，请稍后再试'
        };
      }
    },

    // 更新个人简介
    async updateUserBio(bio) {
      try {
        if (!this.token && !this.refreshToken) {
          return { success: false, message: '未登录' };
        }

        const response = await this.requestWithAuth({
          method: 'put',
          url: `${apiConfig.baseURL}/api/user/update`,
          data: { bio }
        });

        if (response.data && response.data.code === 200) {
          if (this.userInfo) {
            this.userInfo.bio = bio;
          }
          return { success: true, message: '更新个人简介成功' };
        }

        return {
          success: false,
          message: response.data?.message || '更新个人简介失败'
        };
      } catch (error) {
        console.error('更新个人简介请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '更新个人简介请求失败，请稍后再试'
        };
      }
    },

    // 修改密码
    async updatePassword(oldPassword, newPassword) {
      try {
        if (!this.token && !this.refreshToken) {
          return { success: false, message: '未登录' };
        }

        const response = await this.requestWithAuth({
          method: 'put',
          url: `${apiConfig.baseURL}/api/user/password`,
          data: { oldPassword, newPassword }
        });

        if (response.data && response.data.code === 200) {
          // 后端已撤销刷新令牌；本地也清空，要求重新登录
          this._clearAuth();
          return { success: true, message: '密码修改成功，请重新登录' };
        }

        return {
          success: false,
          message: response.data?.message || '密码修改失败'
        };
      } catch (error) {
        console.error('修改密码请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '修改密码请求失败，请稍后再试'
        };
      }
    }
  },

  // pinia-plugin-persistedstate v4 的写法
  persist: {
    key: 'user-store',
    storage: localStorage,
    pick: ['userInfo', 'token', 'refreshToken', 'isLogin']
  }
});
```

说明：

- `token` 字段名保留，所以 `AIChat.vue`、`router/index.js` 里现有的 `userStore.token` 判断不用改。
- `refreshAccessToken` 只有明确 401 才清空登录态；断网/后端挂了不会把用户踢下线。
- `requestWithAuth` 处理 axios 请求的 401 重试；`AIChat.vue` 的 `fetch` 由下一步的 `authFetch` 处理。
- 持久化配置从旧的 v3 `strategies` 写法改成 v4 的 `key/storage/pick`。你项目安装的是 `pinia-plugin-persistedstate@4.7.1`，旧写法很可能没生效；如果你原来的登录态刷新页面后本来就丢失，这一步顺便修好了。

### Step 2：新建 `toutiao_frontend/src/utils/http.js`

`src/utils` 目录不存在就新建：

```js
import axios from 'axios';
import { apiConfig } from '../config/api';
import { useUserStore } from '../store/user';

/**
 * 统一 axios 实例：
 * 1. 自动加 Authorization: Bearer <accessToken>
 * 2. 收到 401 时自动刷新访问令牌，并重试原请求一次
 */
export const http = axios.create({
  baseURL: apiConfig.baseURL,
  timeout: 20000
});

http.interceptors.request.use((config) => {
  const userStore = useUserStore();
  if (userStore.token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${userStore.token}`;
  }
  return config;
});

// 同一时刻只允许一个刷新请求，避免并发 401 触发多次刷新
let refreshPromise = null;

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    if (!original || error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }

    const url = original.url || '';
    const skipUrls = [
      '/api/user/login',
      '/api/user/register',
      '/api/user/refresh',
      '/api/user/logout'
    ];
    if (skipUrls.some((path) => url.includes(path))) {
      return Promise.reject(error);
    }

    const userStore = useUserStore();
    if (!userStore.refreshToken) {
      return Promise.reject(error);
    }

    original._retry = true;

    if (!refreshPromise) {
      refreshPromise = userStore.refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }

    const refreshed = await refreshPromise;
    if (!refreshed) {
      return Promise.reject(error);
    }

    original.headers = original.headers || {};
    original.headers.Authorization = `Bearer ${userStore.token}`;
    return http(original);
  }
);

/**
 * 给 fetch / SSE 用的鉴权封装。
 * EventSource 不能自定义请求头，所以项目里用的是 fetch + ReadableStream，
 * 这里同样可以加 Authorization，并在 401 时刷新重试。
 */
export async function authFetch(url, options = {}) {
  const userStore = useUserStore();

  const buildOptions = () => {
    const headers = new Headers(options.headers || {});
    if (userStore.token) {
      headers.set('Authorization', `Bearer ${userStore.token}`);
    }
    return { ...options, headers };
  };

  let response = await fetch(url, buildOptions());

  if (response.status === 401 && userStore.refreshToken) {
    const refreshed = await userStore.refreshAccessToken();
    if (refreshed) {
      response = await fetch(url, buildOptions());
    }
  }

  return response;
}
```

注意：

- `http.js` 里调用 `useUserStore()` 必须发生在 Pinia 安装之后；请求都是用户操作触发的，满足条件。
- `store/user.js` 没有 import `http.js`，所以不存在循环依赖。
- 并发 401 时用 `refreshPromise` 合并刷新，避免多个请求同时刷新把刷新令牌用乱（本方案刷新不轮换，但合并仍然是好习惯）。

### Step 3：修改 `toutiao_frontend/src/store/modules/favorite.js`

这个文件有 5 处 axios 调用。按下面替换：

**（1）文件头**

```js
import { defineStore } from 'pinia';
import { http } from '../../utils/http';
import { useUserStore } from '../user';
```

删掉原来的：

```js
import axios from 'axios';
import { apiConfig } from '../../config/api';
```

**（2）检查收藏状态**

```js
const response = await http.get('/api/favorite/check', {
  params: { newsId }
});
```

**（3）添加收藏**

```js
const response = await http.post('/api/favorite/add', { newsId });
```

**（4）取消收藏**

```js
const response = await http.delete('/api/favorite/remove', {
  params: { newsId }
});
```

**（5）清空收藏**

```js
const response = await http.delete('/api/favorite/clear');
```

**（6）收藏列表**

```js
const response = await http.get('/api/favorite/list', {
  params: { page, pageSize }
});
```

其余业务代码（登录判断、本地收藏、`try/catch`）不动。`userStore` 仍然保留，因为还要判断 `getLoginStatus`。

### Step 4：修改 `toutiao_frontend/src/store/modules/history.js`

同样处理 4 处调用。

**（1）文件头**

```js
import { defineStore } from 'pinia';
import { http } from '../../utils/http';
import { useUserStore } from '../user';
```

删掉 `import axios from 'axios';` 和 `import { apiConfig } ...`。

**（2）添加历史**

```js
const response = await http.post('/api/history/add', { newsId });
```

**（3）清空历史**

```js
const response = await http.delete('/api/history/clear');
```

**（4）删除单条**

```js
const response = await http.delete(`/api/history/delete/${id}`);
```

**（5）历史列表**

```js
const response = await http.get('/api/history/list');
```

### Step 5：修改 `toutiao_frontend/src/views/AIChat.vue`

**（1）文件头新增**

```js
import { authFetch } from '../utils/http';
```

**（2）聊天 SSE**（约 242 行）

把：

```js
const response = await fetch(aiChatConfig.chatEndpoint, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': userStore.token
  },
  body: JSON.stringify({ message: userMessage })
});
```

改成：

```js
const response = await authFetch(aiChatConfig.chatEndpoint, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ message: userMessage })
});
```

**（3）历史列表**（约 359 行）

把：

```js
const response = await fetch(
  `${aiChatConfig.historyEndpoint}?page=${historyPage.value}&pageSize=10`,
  {
    headers: { Authorization: userStore.token }
  }
);
```

改成：

```js
const response = await authFetch(
  `${aiChatConfig.historyEndpoint}?page=${historyPage.value}&pageSize=10`
);
```

**（4）清空历史**（约 410 行）

把：

```js
const response = await fetch(aiChatConfig.historyEndpoint, {
  method: 'DELETE',
  headers: { Authorization: userStore.token }
});
```

改成：

```js
const response = await authFetch(aiChatConfig.historyEndpoint, {
  method: 'DELETE'
});
```

原有的 401 处理逻辑保留：如果 `authFetch` 刷新也失败，仍然返回 401，前端会 `logout()` 并跳登录页。

### Step 6：修改 `toutiao_frontend/src/views/Profile.vue`

**（1）修正账号 ID 显示**

把：

```js
const userId = computed(() => userStore.token ? userStore.token.substring(0, 5) : '');
```

改成：

```js
const userId = computed(() => userStore.userInfo?.id ?? '');
```

JWT 的 `sub` 是用户 ID，但 token 字符串前 5 位是 `eyJhb`，不能再拿来当 ID；直接用后端返回的 `userInfo.id`。

**（2）改密成功后跳登录页**

把：

```js
if (result && result.success) {
  showSuccessToast('密码修改成功');
} else {
```

改成：

```js
if (result && result.success) {
  showSuccessToast(result.message || '密码修改成功，请重新登录');
  router.push('/login');
} else {
```

因为后端改密时撤销了刷新令牌，本地 `updatePassword` 也清空了登录态，必须重新登录。

**（3）顺手清理未使用的 import（可选）**

`Profile.vue` 顶部有：

```js
import axios from 'axios';
import { apiConfig } from '../config/api';
```

这个文件里没有直接使用它们，可以删掉。

### Step 7：修改 `toutiao_frontend/src/router/index.js`（可选）

当前守卫：

```js
if (to.meta.requiresAuth && !userStore.token) {
```

建议改成：

```js
if (to.meta.requiresAuth && !userStore.token && !userStore.refreshToken) {
```

含义：只要还有刷新令牌，就允许进入页面；页面里的第一个 API 请求会自动刷新访问令牌。如果刷新也失败，`authFetch` / `http` 会返回 401，页面再跳登录。

### Step 8：前端自测

启动前端：

```powershell
cd D:\vscodeproject\HelloFastAPI\toutiao_frontend
npm run dev
```

按顺序检查：

1. **登录**：打开 `http://localhost:5173/login`，用 `admin / 123456` 登录。F12 → Network → `login` 响应里应该有 `accessToken`、`refreshToken`、`userInfo`。
2. **本地存储**：F12 → Application → Local Storage → `http://localhost:5173` → `user-store`，应该能看到 `token`、`refreshToken`、`isLogin`。
3. **请求头**：点开任意需要登录的请求（如 `/api/user/info`），Request Headers 应该是 `Authorization: Bearer eyJ...`，不再是裸 token。
4. **刷新页面**：按 F5，登录态应该还在（Pinia 持久化生效）。
5. **自动刷新**：把后端 `.env` 的 `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` 改成 `1`，重启后端，重新登录，等 70 秒，然后点“我的收藏”或“浏览历史”。Network 里应该看到：
   - 原请求 401
   - `POST /api/user/refresh` 200
   - 原请求重试 200
   页面不跳登录，说明自动刷新成功。
6. **登出**：点“退出登录”，Local Storage 清空，跳登录页。再手动调 `/refresh` 用旧刷新令牌，应该 401。
7. **改密**：改密成功后应跳到登录页；用旧密码登录失败，新密码登录成功。
8. **AI 问答**：进入 `/aichat` 提问，SSE 正常流式返回；等访问令牌过期后再提问，应该自动刷新并继续，不报 401。
9. **账号 ID**：个人信息页显示 `ID: heima-1`（真实用户 ID），不再显示 `eyJhb`。

---

## 8. 联调验收清单

把下面每一项都跑一遍，全部通过再算完成：

| # | 场景 | 操作 | 预期 |
| --- | --- | --- | --- |
| 1 | 注册 | 新用户名注册 | 200，返回双令牌和 `userInfo` |
| 2 | 重复注册 | 同名再注册 | 400，`User already exists` |
| 3 | 登录 | 正确账号密码 | 200，返回双令牌 |
| 4 | 错误密码 | 错密码登录 | 401，`Invalid credentials` |
| 5 | 访问受保护接口 | 带 `Bearer <access>` | 200 |
| 6 | 无令牌 | 不带 Authorization | 401，中文提示 |
| 7 | 伪造令牌 | 改 token 一个字符 | 401，`身份凭证无效` |
| 8 | 旧 UUID 令牌 | 用改造前 token | 401 |
| 9 | 访问令牌过期 | 1 分钟有效期，等 70 秒 | 401，`登录已过期` |
| 10 | 刷新令牌 | 用 refresh 换 access | 200，返回新 access |
| 11 | 登出 | 调 `/logout` 后再 refresh | refresh 401 |
| 12 | 二次登录 | 另一设备再登录，旧 refresh 刷新 | 旧 refresh 401 |
| 13 | 改密 | 改密后用旧 refresh | 401 |
| 14 | 前端自动刷新 | 过期后点收藏/历史 | 自动 refresh + 重试成功 |
| 15 | 前端登出 | 点退出登录 | 本地清空、跳登录、旧 refresh 失效 |
| 16 | AI SSE | 登录后提问 | 流式输出正常 |
| 17 | 刷新页面 | F5 | 登录态保持 |
| 18 | Swagger | Authorize 后调 `/info` | 200 |

---

## 9. 常见问题排查

### 9.1 启动报 `RuntimeError: 未配置 JWT_SECRET_KEY`

- 检查 `toutiao_backend/.env` 是否有 `JWT_SECRET_KEY=...`。
- 检查变量名有没有拼错（大小写敏感）。
- 检查 `.env` 是否在 `toutiao_backend` 根目录，而不是项目根目录。
- 改完 `.env` 必须**重启**后端，`--reload` 不一定重载环境变量。

### 9.2 `ModuleNotFoundError: No module named 'jwt'`

装到了别的 Python 环境。确认启动和安装用的是同一个解释器：

```powershell
.\.venv\Scripts\python.exe -m pip install "PyJWT==2.10.1"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

不要用全局 `pip` 装完再用 `.venv` 启动。

### 9.3 所有请求都 401，但登录明明成功

按顺序排查：

1. 前端请求头是不是 `Authorization: Bearer eyJ...`？F12 → Network → Request Headers。
2. `userStore.token` 是不是空？Vue Devtools 或 localStorage 看 `user-store`。
3. 后端和前端是不是连的同一个地址/端口？
4. 后端 `.env` 的 `JWT_SECRET_KEY` 是否在登录后改过？改密钥会让旧 token 全部失效。
5. 是否把 `refreshToken` 当成 access 用了？两者不通用。

### 9.4 `Signature verification failed`

- 签发和校验用的不是同一个 `JWT_SECRET_KEY`（比如一个进程读到了旧 `.env`）。
- 重启后端，确认只有一个 `.env`。
- 如果用了 Docker，检查容器环境变量是否覆盖了 `.env`。

### 9.5 `401` 一直循环刷新

- `/refresh` 本身返回 401，但前端还在重试。检查 `http.js` 的 `skipUrls` 是否包含 `/api/user/refresh`。
- 刷新令牌已过期或被登出删除。清 localStorage，重新登录。
- 后端时间和数据库时间差太多，刷新令牌一签发就“过期”。检查服务器时区/NTP。

### 9.6 刷新令牌一签发就过期

`create_refresh_token()` 用 `datetime.now()`（本地 naive），数据库 `expires_at` 也是 naive。如果应用服务器和 MySQL 不在同一时区，比较会出错。两种解决方式：

- 让应用和 MySQL 都用同一时区（推荐，教学项目最简单）。
- 全部改 UTC：数据库存 UTC，应用用 `datetime.utcnow()` 或 `datetime.now(timezone.utc).replace(tzinfo=None)` 比较。

不要一半 UTC 一半本地时间。

### 9.7 `MultipleResultsFound`

旧代码可能给同一个用户留下多行 `user_token`。新代码登录时会先 `DELETE` 再插入，通常不会再出现。如果还有，执行：

```sql
DELETE FROM `user_token`;
```

或按用户去重：

```sql
DELETE t1 FROM `user_token` t1
JOIN `user_token` t2
  ON t1.user_id = t2.user_id AND t1.id < t2.id;
```

### 9.8 Swagger 里 Authorize 后还是 401

- Swagger 的 HTTPBearer 输入框只填 token 本身，不要填 `Bearer eyJ...`（它会自动加）。
- 确认填的是 `accessToken`，不是 `refreshToken`。
- 确认后端已重启，加载的是新代码。

### 9.9 前端刷新页面后登录态丢失

- `pinia-plugin-persistedstate` 版本是 4.x，旧 `strategies` 写法不生效。按 Step 1 改成 `key/storage/pick`。
- 检查 localStorage 里有没有 `user-store`。
- 如果浏览器隐私模式/清理策略禁用了 localStorage，需要换存储方案。

### 9.10 改密后旧 access 还能用

这是 JWT 的正常行为：后端只撤销了刷新令牌，已签发的访问令牌在 30 分钟内仍然有效。要“立即失效”，看第 10 章的 `token_version` 或 Redis 黑名单。

### 9.11 CORS 报错

`main.py` 已经配置：

```python
allow_origins=["*"],
allow_headers=["*"],
```

`Authorization` 属于自定义头，`allow_headers=["*"]` 能放行。如果换成固定域名，记得把 `Authorization` 加进去。

另外注意：`allow_origins=["*"]` 和 `allow_credentials=True` 在浏览器规范里不能同时用于“带 Cookie 的跨域请求”。本项目用 Authorization 头，不依赖 Cookie，通常没问题；生产环境建议写死前端域名。

### 9.12 令牌太长导致数据库报错

访问令牌不存数据库，不受影响。刷新令牌存的是 64 位哈希，`String(200)` 足够。如果你把刷新令牌改成了 JWT 并直接存明文，才可能超过 200 字符——本方案没有这样做。

---

## 10. 安全加固（可选，但推荐了解）

### 10.1 让访问令牌“立即失效”：`token_version`

JWT 的天然缺点是到期前无法撤销。最简单的补救是给用户加一个版本号：

**（1）数据库**

```sql
ALTER TABLE `user`
  ADD COLUMN `token_version` INT NOT NULL DEFAULT 0 COMMENT '令牌版本号';
```

**（2）模型 `models/users.py`**

```python
token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="令牌版本号")
```

**（3）签发时写入**

```python
def create_access_token(user_id: int, username: str, token_version: int = 0):
    ...
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "access",
        "ver": token_version,
        # ...其余 claims 保持不变...
    }
```

**（4）鉴权时比对**

```python
if int(payload.get("ver", 0)) != user.token_version:
    raise _unauthorized("登录状态已失效，请重新登录")
```

**（5）改密/强制下线时递增**

```python
user.token_version += 1
```

这样改密后所有旧访问令牌立刻失效。代价是每次请求多读一个字段（本来就要查 user 表，成本很低），以及一次 DDL。

### 10.2 Redis 黑名单（按 `jti` 撤销单个访问令牌）

项目已经有 Redis（`config/cache_conf.py`）。登出时把当前访问令牌的 `jti` 写入黑名单，TTL 设为访问令牌剩余有效期：

```python
# 登出时（需要能拿到当前 access 的 payload）
await redis_client.setex(f"jwt:blacklist:{jti}", ttl, "1")

# 鉴权时
if await redis_client.exists(f"jwt:blacklist:{payload['jti']}"):
    raise _unauthorized("登录状态已失效")
```

优点：可以精确撤销某一个访问令牌。
缺点：每次请求多一次 Redis 查询，重新引入“有状态”；Redis 挂了要考虑降级策略。

### 10.3 刷新令牌轮换（Rotation）

当前方案刷新令牌 7 天内不变。更安全的做法是“每次刷新都换一个新的刷新令牌”：

1. `/refresh` 校验旧 refresh。
2. 删除旧行，生成新 refresh + 新哈希，插入新行。
3. 响应同时返回新的 `accessToken` 和 `refreshToken`。
4. 如果旧 refresh 被再次使用（说明可能被盗），撤销该用户全部会话。

这能检测刷新令牌盗用，但实现和前端状态更新更复杂。教学项目可以先用当前方案，理解后再加。

### 10.4 用 httpOnly Cookie 存刷新令牌

localStorage 的最大风险是 XSS。生产级方案：

- 访问令牌放内存（不落 localStorage）。
- 刷新令牌放 `HttpOnly; Secure; SameSite=Strict` Cookie。
- 刷新接口从 Cookie 读刷新令牌，配合 CSRF Token。

这样 JS 读不到刷新令牌，XSS 危害大幅降低。代价是跨域 Cookie、CORS、CSRF 配置更复杂。本项目前后端分离且本地开发，先用 localStorage 可以接受，但要知道风险。

### 10.5 其他清单

- **HTTPS**：生产必须；HTTP 下 Authorization 头是明文。
- **不要记录完整令牌**：日志里打日志只打前 8 位或 `jti`。
- **登录限流**：防暴力破解，按 IP + 用户名限流。
- **密码策略**：bcrypt 已有；限制长度 72 字节（bcrypt 上限）。
- **密钥轮换**：换 `JWT_SECRET_KEY` 会让所有访问令牌失效，适合“全站强制下线”。
- **依赖审计**：定期 `pip-audit` / `npm audit`。
- **JWT 不放敏感信息**：Payload 可解码。
- **算法固定**：永远显式 `algorithms=["HS256"]`。
- **`iss`/`aud` 校验**：多服务时加 `aud`，防止 A 服务的 token 拿到 B 服务用。
- **时钟同步**：服务器开 NTP，验签留 leeway。

### 10.6 什么时候该上 RS256

- 多个后端服务需要独立验签，但不想共享同一个密钥。
- 第三方需要验证你签发的令牌。
- 密钥泄露面要收敛到“只有授权服务器持有私钥”。

做法：授权服务用私钥签，其他服务用公钥验。PyJWT 支持：

```python
jwt.encode(payload, private_key_pem, algorithm="RS256")
jwt.decode(token, public_key_pem, algorithms=["RS256"])
```

单体项目用 HS256 足够，不必过度设计。

---

## 11. 回滚方案

改造没有数据库结构变更，回滚很轻：

1. **代码回滚**

```powershell
cd D:\vscodeproject\HelloFastAPI
git switch main
# 或
git checkout -- toutiao_backend toutiao_frontend README.md requirements.txt
```

如果是手动备份，把备份目录覆盖回来。

2. **删除新增文件**

```text
toutiao_backend/config/jwt_config.py
toutiao_backend/utils/jwt_utils.py
toutiao_frontend/src/utils/http.js
```

3. **`.env` 保留 JWT 配置也无害**，旧代码不读它；想干净就删掉那几行。

4. **数据库**

```sql
DELETE FROM `user_token`;
```

旧代码会重新生成 UUID token；用户重新登录即可。

5. **前端**

如果已经 `npm run build`，回滚源码后重新 build；开发模式 `npm run dev` 会自动热更新。

6. **重启后端**

```powershell
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

---

## 12. 附录

### 12.1 一段 JWT 的完整示例

Header：

```json
{"alg":"HS256","typ":"JWT"}
```

Payload：

```json
{
  "sub": "1",
  "username": "admin",
  "type": "access",
  "jti": "8f14e45fceea167a5a36dedd4bea2543",
  "iss": "toutiao-api",
  "iat": 1730000000,
  "exp": 1730001800
}
```

签名计算（伪代码）：

```text
signing_input = base64url(header) + "." + base64url(payload)
signature     = base64url(HMAC_SHA256(signing_input, JWT_SECRET_KEY))
token         = signing_input + "." + signature
```

### 12.2 本地解码 JWT（不验签，只看内容）

Python：

```python
import jwt

token = "eyJ..."
print(jwt.decode(token, options={"verify_signature": False}))
```

或打开 <https://jwt.io> 粘贴（不要在生产令牌上操作）。

### 12.3 术语表

| 术语 | 含义 |
| --- | --- |
| JWT | JSON Web Token，带签名的 JSON 令牌 |
| Claim | JWT payload 里的一个字段，如 `sub`、`exp` |
| HS256 | HMAC-SHA256，对称签名算法，签发和校验用同一个密钥 |
| RS256 | RSA-SHA256，非对称签名，私钥签、公钥验 |
| Access Token | 访问令牌，短期，用于业务请求 |
| Refresh Token | 刷新令牌，长期，用于换新的访问令牌 |
| Bearer | RFC 6750 定义的令牌使用方式：`Authorization: Bearer <token>` |
| `jti` | JWT ID，令牌唯一标识，可用于黑名单 |
| `sub` | Subject，令牌主体，本方案存用户 ID |
| `iss` | Issuer，签发者 |
| `exp` | Expiration Time，过期时间（Unix 秒） |
| `iat` | Issued At，签发时间（Unix 秒） |

### 12.4 最小验证路径（赶时间版）

如果你只想先跑通，不做自动刷新：

1. 后端按 Step 1～9 改完。
2. 前端只改 `store/user.js` 的登录/注册解析（`accessToken`）和 3 个 `user.js` 请求头为 `Bearer`。
3. `favorite.js` / `history.js` / `AIChat.vue` 的裸 token 先不动——后端 `get_current_user` 兼容裸 `<jwt>`，所以还能用。
4. 访问令牌设成 7 天（`JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080`），暂时不接刷新。
5. 跑通后再按 Step 2、3、4、5 加 `http.js` 和自动刷新，把有效期改回 30 分钟。

这样风险最低，但最终仍建议完成完整方案。

---

## 13. 本次改造“顺手发现”的其他问题

这些不是 JWT 的核心，但改到这里可以一起处理：

1. **`UserChangePasswordRequest.new_password` 的 `max_length=6`**
   这会把 7 位以上的新密码判为非法。本文已改为 `min_length=6, max_length=72`。

2. **`Profile.vue` 用 token 前 5 位当账号 ID**
   JWT 下会显示 `eyJhb`。本文已改为 `userStore.userInfo?.id`。

3. **`pinia-plugin-persistedstate` 版本与写法不匹配**
   安装的是 4.7.1，但 `store/user.js` 用的是 v3 的 `strategies`。本文已改为 v4 的 `key/storage/pick`。

4. **`create_user_token` 更新分支没有 commit**
   旧代码靠 `get_db()` 兜底提交；本文所有写操作都显式 `commit()`。

5. **`get_current_user` 的 `replace("Bearer ", "")` 过于宽松**
   它会替换字符串中任意位置的 `Bearer `；本文改为严格解析 scheme + credentials。

6. **`main.py` 的 CORS `allow_origins=["*"]` + `allow_credentials=True`**
   浏览器规范下带 Cookie 的跨域会被拒绝。当前用 Authorization 头不受影响；生产建议写死域名。

---

## 14. 最后总结

这次改造的本质不是“把 UUID 换成 JWT”，而是把认证拆成两层：

- **短期、无状态、可验签的 Access Token**：负责高频业务请求，性能好。
- **长期、有状态、可撤销的 Refresh Token**：负责续期和登出，安全可控。

记住三句话：

1. **JWT 只保证“没被改过”，不保证“没被看到”**——不要放敏感信息。
2. **JWT 的签名密钥就是最高权限**——放 `.env`、用 HTTPS、别提交 git。
3. **JWT 不能天然撤销**——短有效期 + 刷新令牌撤销 +（可选）版本号/黑名单，才是完整方案。

按本文顺序做，每完成一个阶段就用第 8 章的验收清单自测；出问题先看第 9 章。改造完成后，你对“登录态”这件事的理解会比只会用 Session 深一层。
