# Ops Console

轻量级站点运维与诊断平台（内部工具）：SSH 只读采集 Linux 指标、Redis 浏览（唯一可写资源）、ActiveMQ Artemis（Jolokia）、设备 HTTP 接入、总览健康检查与操作日志。

- 无用户系统 / 无登录（内网部署定位）
- 对目标服务器**只读**（SSH 命令白名单，无用户输入命令）；Redis 删除类操作走倒计时确认
- 所有外呼：超时 + 有界重试 + 按资源类型/按主机并发限流；错误统一信封，单资源故障不影响其他功能

## 目录结构

```
backend/          FastAPI（Python 3.13，uv 管理依赖），入口 backend/app/main.py
  app/modules/    功能模块（sites/server/redis/mq/device/overview/audit/ssh/testconn/database）
frontend/         Vue 3 + TypeScript + Vite（naive-ui / pinia / echarts / vue-i18n 中英双语）
deploy/           Dockerfile.nginx + nginx.conf（前端托管 + /api 反代）
scripts/          e2e_live.py（对真实资源的端到端脚本）
compose.yaml      一键部署（backend + ops-nginx；复用现有 Redis）
```

## 环境配置

复制 `.env.example` 为 `.env` 并填入真实值（**`.env` 已 gitignore，绝不入库**）：

```bash
cp .env.example .env
```

| 变量 | 必填 | 说明 |
|---|---|---|
| `OPS_REDIS_URL` | ✅ | 平台 Redis（配置/缓存/锁/操作日志），建议独立 DB，如 `redis://host:6379/5` |
| `OPS_PORT` |  | 部署宿主机端口（默认 25089） |
| `OPS_LOG_LEVEL` |  | 日志级别（默认 INFO） |
| `SSH_COMMAND_TIMEOUT` 等 |  | 外部系统超时（秒），默认值见 `backend/app/core/config.py` |
| `ARTEMIS_*` / `SERVER_*` |  | 仅 E2E 脚本使用，可选 |

## 本地开发

```bash
uv sync                                  # 安装后端依赖（.venv）
uv run --env-file .env python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 25088

cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 25089                            # http://localhost:25089，/api 代理到 :25088
```

测试：

```bash
uv run pytest                            # 后端（fakeredis，不依赖真实服务）
cd frontend && npx vitest run            # 前端
uv run --env-file .env python scripts/e2e_live.py   # 真实资源 E2E（先起 8123 后端，见 scripts 注释）
```

## 生产部署

```bash
docker compose up -d --build
```

- 构建两个镜像：`ops-backend`（uv 装依赖 + uvicorn:8000）与 `ops-nginx`（Node 构建前端 dist → nginx 托管 + `/api` 反代到 ops-backend）
- **Redis 不在 compose 内**——复用现场现有 Redis，通过 `.env` 的 `OPS_REDIS_URL` 接入
- 访问 `http://<host>:${OPS_PORT:-25089}`
- `nginx.conf` 的 `/api` 读超时为 300s（SSH 执行预算 60s、SSE 流式执行需要长连接）

### 端口说明（常见困惑）

| 端口 | 出现场景 | 说明 |
|---|---|---|
| `5173` | 仅本地开发 | vite 开发服务器默认端口；本仓库实际用 `25089` 起前端（`/api` 代理到本机 `127.0.0.1:25088`）；**部署时不存在** |
| `8000` | 仅容器内部 | uvicorn 监听容器内端口；ops-nginx 经 **docker 内网**以服务名 `http://ops-backend:8000` 访问，**与宿主机端口映射无关** |
| `OPS_PORT`（25089） | 唯一公网端口 | 浏览器只访问它：nginx 返回前端页面并把 `/api` 反代给 backend |

要点：**前端不是独立部署的服务**——它与 nginx 打包为同一镜像（ops-nginx）。backend 无需任何宿主机端口映射（Portainer 里映射 8000 纯属多余，还会把 API 绕过 nginx 直接暴露）。

### CI/CD（Jenkins 等）部署注意

compose 的 `.env` 自动读取只认**运行命令的目录**；`.env` 不入库，所以 CI 检出的工作区里没有它，`${OPS_REDIS_URL}` 会插值成空串（用 `docker compose config | grep OPS_REDIS_URL` 可验证）。解法任选：

1. **凭据注入（推荐）**——插值优先级是 shell 环境变量 > `.env`，Jenkins pipeline 里：
   ```groovy
   withCredentials([string(credentialsId: 'ops-redis-url', variable: 'OPS_REDIS_URL')]) {
     sh 'docker compose up -d --build'
   }
   ```
   必填的只有 `OPS_REDIS_URL`，其余变量均有默认值。
2. **固定路径**：`.env` 手工放部署机固定位置（如 `/srv/ops/.env`），命令改 `docker compose --env-file /srv/ops/.env up -d --build`。

### 用 Portainer 部署

Portainer 本质是 compose 的 UI，不要单独起 backend 容器：

1. Stacks → Add stack → 粘贴本仓库 `compose.yaml`
2. Environment variables 填入 `.env` 各项（`OPS_REDIS_URL` 必填、`OPS_PORT` 按需）
3. Deploy the stack——backend 与 ops-nginx 自动同内网，`backend:8000` 服务名解析成立
4. 访问 `http://<host>:OPS_PORT`

## 注意事项

- **Windows 开发机不要给 uvicorn 加 `--reload`**：仓库被 IDE 触碰时 StatReload 会卡死（监听端口消失、Ctrl+C 失效），直接不带 `--reload` 运行
- 平台 Redis（`OPS_REDIS_URL`）与被监控业务 Redis 严格隔离：业务连接由 redis 模块按站点配置每次新建、用毕即关
- 操作日志保留最近 320 条；趋势采样 key 写入即续期 2h TTL，无读者自动消亡
- 新增功能模块 = `backend/app/modules/<name>/` + `frontend/src/modules/<name>/` 各一处注册，不改 main.py / 布局 / 路由（参见 database 占位模块）

## 文档

- `docs/prd-tech-design-v0.2.md` — 基线 PRD / 技术设计
- `docs/ui-upgrade-design.md` — 前端视觉与交互升级基准
- `CLAUDE.md` — 面向 AI 协作的开发约定
