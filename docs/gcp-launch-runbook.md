# GCP 上线操作手册（Firebase Hosting + Cloud Run）

本文当前阶段追求最快完成小范围端到端测试。前端已经以 hosting-only 方式发布到 Firebase；后端使用单实例 Cloud Run、本地 SQLite 和 Cookie Session。Cloud SQL 与 Redis 延后，测试数据允许随实例停止或部署而全部丢失。

## 0. 当前架构和状态

```text
Firebase Hosting
  └─ React SPA（已发布，尚未连接 API）

Cloud Run disposable test Service
  └─ Flask / Gunicorn API
      ├─ 每次启动自动 migration 的临时 SQLite
      └─ Cookie Session + 进程内限流
```

固定资源名：

| 配置                    | 值                                                                        |
| ----------------------- | ------------------------------------------------------------------------- |
| GCP project             | `auspicious-silo-492102-j6`                                               |
| Region                  | `us-central1`                                                             |
| Firebase site           | `ergonosis-extraction-portal`                                             |
| Artifact Registry       | `portal`                                                                  |
| Image                   | `extraction-portal`                                                       |
| Cloud Run Service       | `extraction-portal`                                                       |
| Runtime service account | `extraction-portal-run@auspicious-silo-492102-j6.iam.gserviceaccount.com` |

后端是请求驱动的 HTTP 服务，不需要常驻实例。Cloud Run 配置为 `minScale=0` 和 request-based CPU。未来的定期同步应使用 Cloud Run Job + Scheduler。

## 1. 一次性创建 GCP 资源

### 1.1 Artifact Registry

在 GCP Console 的 Artifact Registry 中创建：

- Name：`portal`
- Format：Docker
- Region：`us-central1`
- Tag immutability：关闭

最终镜像地址：

```text
us-central1-docker.pkg.dev/auspicious-silo-492102-j6/portal/extraction-portal
```

### 1.2 Secret Manager 和运行账号

创建运行账号：

```text
extraction-portal-run@auspicious-silo-492102-j6.iam.gserviceaccount.com
```

Secret Manager 至少存在：

- `SECRET_KEY`
- `FERNET_KEY`

只对这两个 Secret 给运行账号授予 Secret Manager Secret Accessor。生产模式缺少任一 Secret 时会拒绝启动。

### 1.3 占位 Cloud Run Service

在 Cloud Run Console 创建：

- Service：`extraction-portal`
- Region：`us-central1`
- Placeholder image：`us-docker.pkg.dev/cloudrun/container/hello`
- Authentication：Require authentication
- Ingress：All
- Runtime service account：`extraction-portal-run`
- CPU / Memory：1 / 512 MiB
- Concurrency：8
- Timeout：60 seconds
- Min / Max instances：0 / 1
- CPU allocation：Only during request processing

首次 GitHub 部署会用 `infra/portal/cloudrun.yaml` 完整替换占位 revision。IAM policy 不属于 manifest，Service 仍保持私有。

## 2. GitHub Actions 无密钥权限

复用项目已有 provider：

```text
projects/111021901996/locations/global/workloadIdentityPools/bot-identity-pool/providers/github-provider
```

该 provider 已允许 `Ergonosis` owner。给当前仓库 principal 补三项资源级权限：

- Artifact Registry `portal`：`roles/artifactregistry.writer`
- Cloud Run Service `extraction-portal`：`roles/run.developer`
- Runtime service account：`roles/iam.serviceAccountUser`

完整命令位于 `infra/README.md`。不创建 GCP JSON key，也不需要 GitHub Actions secret。

## 3. 仓库部署结构

| 文件                                    | 作用                                            |
| --------------------------------------- | ----------------------------------------------- |
| `.env.dev`                              | 已提交的非敏感项目、区域、服务、镜像和 WIF 标识 |
| `infra/portal/Dockerfile`               | API-only production image，不包含 React SPA     |
| `infra/portal/cloudrun.yaml`            | Cloud Run Service 唯一配置来源                  |
| `.github/workflows/deploy-backend.yaml` | 测试、构建、推送和部署不可变 digest             |
| `infra/README.md`                       | Console、WIF、验证与回滚操作                    |

Workflow 在以下情况下触发：

- 后端构建输入合并到 `main`；
- 在 GitHub Actions 中手动运行 `Deploy Extraction Backend`。

Portal、Firebase 或文档独立变更不会触发后端部署。

## 4. 首次后端部署

1. 确认第 1 节资源已经创建。
2. 执行 `infra/README.md` 中的 WIF IAM 命令。
3. 打开 GitHub → Actions → **Deploy Extraction Backend**。
4. 选择当前部署分支并运行 workflow。

Workflow 会：

1. 校验 `uv.lock`、同步锁定依赖并执行 `uv run --locked python -m pytest`；
2. 使用 WIF 获取短期 GCP credentials；
3. Buildx 构建 `infra/portal/Dockerfile`；
4. 推送完整 Git SHA 和 `latest` 标签；
5. 获取镜像 digest；
6. 临时把 manifest 中的 `:latest` 替换成 digest；
7. 同步执行 `gcloud run services replace`；
8. 等待 Ready revision，并确认 Service 实际引用本次 digest。

部署成功后，GitHub Step Summary 会显示 commit、digest、revision 和 Service URL。

## 5. 验证私有 Cloud Run

```bash
export GCP_PROJECT_ID=auspicious-silo-492102-j6
export GCP_REGION=us-central1
export SERVICE_NAME=extraction-portal
export SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${GCP_PROJECT_ID}" \
  --region="${GCP_REGION}" \
  --format='value(status.url)')"

curl --fail --show-error --silent --include \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${SERVICE_URL}/api/health"
```

验收条件：

- HTTP `200`；
- `status` 为 `ok`；
- `flask_env` 为 `production`；
- `dev_login_enabled` 为 `false`；
- 响应包含 `Cache-Control: no-store`；
- Cloud Run latest Ready revision 使用 GitHub Summary 中的 digest；
- Service 仍然 Require authentication；
- Firebase 仍是 hosting-only 配置。

私有健康检查通过后，可以进入下一节接通 Firebase。SQLite 中的用户和连接数据不提供保留保证。

## 6. 接通 Firebase 进行一次性数据测试

这一步仍需由操作者明确执行，本地文件修改不会自动改变 GCP：

1. 配置 `MS_CLIENT_ID`、`MS_CLIENT_SECRET`；需要 Plaid 时再配置 Plaid credentials；
2. 在 Entra 注册 Firebase 域名下的登录和 Graph callback；
3. 将 Cloud Run 改为允许 Firebase 调用；
4. 发布仓库根目录 `firebase.json`，打开 `/api/**` rewrite；
5. 验证登录、CSRF mutation、Plaid/Graph 连接和登出。

测试期间必须接受以下行为：

- scale-to-zero 后可能出现全新空数据库；
- 每次新 revision 都从空 schema 开始；
- 用户需要重新登录并重新连接第三方账号；
- 限流只在单个 Gunicorn worker 内准确，不用于压测或安全评估；
- 导出文件仍不能依赖容器本地目录保存。

## 7. 自动重部署与回滚

后端相关代码进入 `main` 后自动运行同一 workflow。生产 Service 永远引用不可变 digest；`latest` 只用于镜像浏览和人工定位。

回滚步骤：

1. Cloud Run Console 打开 `extraction-portal` → Revisions；
2. 选择上一个 Ready revision；
3. 将流量切回该 revision；
4. 验证带身份令牌的 `/api/health`；
5. 如需产生新的 revision，在旧 Git ref 上手动运行 workflow。

不要通过修改 `latest` 标签回滚，Cloud Run revision 不依赖该标签。

## 8. Disposable test 限制

`infra/portal/cloudrun.yaml` 当前明确包含：

```text
DATABASE_URL=sqlite:////tmp/portal-test.db
REDIS_URL=
```

`AUTO_MIGRATE_ON_START=true` 时，Flask app factory 会执行 Alembic upgrade，所以空实例可以自行创建 schema。两个 Gunicorn workers 使用 `/tmp` 文件锁串行执行；第一个完成后，第二个只做 Alembic no-op。Cloud Run 文件系统是临时的；SQLite 文件会随实例停止而丢失。没有 Redis 时 Flask 使用签名 Cookie Session，限流状态只保存在 worker 内存。`maxScale=1` 避免多个实例产生不同数据库，但不改变数据易失性。

## 9. 后续生产化顺序

一次性数据测试完成、需要保留真实数据时：

1. 创建 Cloud SQL、数据库用户、自动备份、PITR 和 deletion protection；
2. 创建 Redis / Memorystore 和 Cloud Run 私网访问；
3. 在 `cloudrun.yaml` 中设置 `AUTO_MIGRATE_ON_START=false`，替换临时 `DATABASE_URL`、`REDIS_URL` 并补网络 annotation；
4. 配置 `MS_CLIENT_ID`、Plaid 和其他 Secret；
5. 使用 `deploy/migrate-cloud-run-job.sh` 执行迁移；
6. 手动运行后端 workflow，验证 DB、Redis、登录和集成；
7. 删除 SQLite 测试数据迁移设想，要求测试用户重新连接；
8. 从 Firebase 域名重新完成登录、CSRF、连接和登出冒烟测试。

导出功能开放前，还必须将 Plaid/Graph 结果持久化到 Cloud Storage；容器本地文件不能作为真实数据存储。
