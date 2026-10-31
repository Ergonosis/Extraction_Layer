# GCP 首次上线：Firebase Hosting + 多实例 Cloud Run + Cloud SQL

本手册取代一次性 SQLite 测试部署。首次上线没有旧数据搬迁，但必须先创建
业务、session 和限流表。运行依赖版本差异不作为本轮上线阻碍。

## 1. 准备资源与权限

项目为 `auspicious-silo-492102-j6`，区域为 `us-central1`。人工准备所需 API、
Artifact Registry `portal`、Cloud SQL PostgreSQL、数据库及用户、Secret Manager
和运行身份。配置备份、按恢复目标选择 PITR、删除保护及连接预算。

数据库 URL 放在 Secret Manager，可使用 Cloud Run 内置认证连接的 socket：

```text
postgresql+psycopg://USER:PASSWORD@/DATABASE?host=/cloudsql/PROJECT:REGION:INSTANCE
```

设置 `SECRET_KEY`、`FERNET_KEY`、`MS_CLIENT_SECRET`；使用 Plaid 时再设置
`PLAID_SECRET`。运行身份需要 Cloud SQL Client 和必要 secrets 的访问权限。
GitHub WIF 发布身份还需镜像写入、Service/Job 部署与执行、使用运行身份、
设置 Service 调用策略，以及 Cloud SQL/secret metadata 读取权限。
前端发布身份还需 Firebase Hosting 发布权限和 Cloud Run metadata 读取权限。

无需为默认方案创建 Memorystore、VPC Connector、Cloud Build 或 Scheduler。
强制私网时使用 Direct VPC egress 并配置相应网络。

## 2. 设置 GitHub variables

| Variable | 值 |
| --- | --- |
| `CLOUD_SQL_INSTANCE` | 同项目同区域的 `project:region:instance` |
| `DATABASE_URL_SECRET` | 保存 PostgreSQL URL 的 Secret Manager secret ID |
| `MS_CLIENT_ID` | Entra app client ID |
| `PLAID_CLIENT_ID` | 可选；配置后 preflight 同时检查 PLAID_SECRET |

项目、区域、运行身份和 WIF provider 来自 `.env.dev`。生产 manifest 中的
placeholder 由 workflow 替换；不能把未替换的文件直接部署。

## 3. 首次发布顺序

1. 手动运行 **Deploy Extraction Backend**，选择审查过的 ref。
2. workflow 检查必填变量、Cloud SQL RUNNABLE 状态和 secrets ENABLED 状态。
   配置缺失、API 未启用、资源不可访问时立即失败，不创建资源，也不自动启用 API。
3. 检查通过后构建并推送 API 镜像，取得不可变 digest。
4. 使用相同 digest 执行 schema Job，等待 `flask db upgrade` 成功。
5. 发布 Cloud Run Service，等待 Ready，核对 revision digest 和生产健康响应。
6. 配置浏览器调用权限；业务认证继续由 session、CSRF 和租户校验执行。
7. API 就绪后运行 **Deploy Extraction Frontend**，只构建静态文件并发布 Hosting。
   前端 workflow 先检查 API Ready 和匿名健康响应，不会重建或发布 API 镜像。

也可以由操作者明确执行本地前端发布：

```bash
bash deploy/build-portal-local.sh
firebase deploy --only hosting
```

后续前端更新只发布 Hosting，后端更新只运行后端 workflow。普通 feature
分支 push 不触发后端部署；进入 main 后由现有路径规则触发。

## 4. Session、限流与连接预算

默认 `SESSION_BACKEND=sqlalchemy`、`RATELIMIT_STORAGE_BACKEND=sqlalchemy`。
`002_sessions_rate_limits` 创建两个共享状态表。session 使用固定 ORM 模型，
应用启动不执行建表；限流保留 fixed-window 额度，通过数据库时间与原子 upsert
实现，并复用业务连接池。未知 backend 配置启动失败，不回退到内存。

默认两个 workers、pool 5 + overflow 5、最多 10 实例，理论池上限 200；
还须为建表 Job、维护连接、扩容和 revision 重叠留余量。根据数据库能力调整
实例上限与池配置。单区域数据库可中断，多实例 API 本身不能提供数据库 HA。

Redis 仍是显式备选：设置相应 backend 为 redis 并提供 REDIS_URL，按需要配置
私网访问。PostgreSQL 与 Redis 等价验证失败时，不得以 memory:// 替代。

## 5. Firebase 与第三方回调

保留 `.firebaserc` 项目和 `ergonosis-extraction-portal` Hosting site。
使用 `firebase.json`，其 `/api/**` rewrite 指向同区域 extraction-portal。
`firebase.hosting-only.json` 仅用于静态准备，不接通 API。

Entra 注册 Hosting 域名下的 `/api/auth/callback` 与 `/api/msgraph/callback`。
页面经同源 rewrite 调用 API，cookie 名必须是 `__session`。API 始终 no-store，
HTML 不长缓存，hash 静态资源可以长缓存；CSP 允许 Plaid CDN。

Plaid export 返回 `{filename, item_id, export, integration}`，不返回容器路径。
临时文件请求内清理；Graph 保持 JSON 响应。同步导出必须在 Firebase 的 60 秒
代理时限内完成并留余量；提高 Cloud Run timeout 无法延长此限制。

## 6. 上线验收与本轮验证范围

本轮允许运行纯 Python/mock/文件系统测试，但跳过 Docker、DB、Redis、GCP
测试。不构建或发布项目。mock 测试验证代码调用与错误分支，不证明真实 SQL。

首次上线前仍须验证：空库建表与重复执行、跨实例 OAuth A→B、SID 轮换与登出
撤销、并发请求不会恢复旧 session、共享限流与 Redis 基准等价、非 UTC 数据库
时区、数据库故障、连接预算、Firebase cookie/cache、第三方连接及导出时限。

## 7. 后续生产化顺序

按明确需要增加 Cloud Storage、可靠异步导出或 Cloud SQL HA。小型即时导出
不提前加对象存储；session 与限流清理可先使用应用 CLI，未配置自动 Scheduler。
回滚到上一个 Ready revision 前需确认 schema 向后兼容；前端与后端分别保留
发布记录并保持 API 兼容旧 SPA。
