# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

轻量级站点运维与诊断平台（内部工具）：SSH 只读采集 Linux 指标、Redis 浏览（唯一可写资源）、ActiveMQ Artemis（Jolokia）、设备（Device）HTTP 接入、总览健康检查与操作日志。无用户系统、无登录（内网定位）。部署与开发指南见 `README.md`。

## Commands

```bash
# 后端（Python 3.13 + uv）
uv sync                                                       # 装依赖到 .venv
uv run --env-file .env python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
uv run pytest backend/tests -q                                # 后端测试（fakeredis，不依赖真实服务）
uv run pytest backend/tests/test_device.py -q                 # 单个文件
uv run pytest backend/tests/test_device.py::test_xxx -q       # 单个用例

# 前端（在 frontend/ 下）
npm run build                                                 # vue-tsc + vite（类型检查含在内）
npx vitest run                                                # 前端测试

# 真实资源 E2E（需 .env 的 ARTEMIS_*/SERVER_*，后端先起在 8123）
uv run --env-file .env python -m uvicorn backend.app.main:app --port 8123
uv run --env-file .env python scripts/e2e_live.py

# 部署（复用现场 Redis，不自带）
docker compose up -d --build                                  # nginx 在 ${OPS_PORT:-8090}
```

**Windows 开发机硬性约束**：uvicorn 不要加 `--reload`——仓库被 IDE 触碰时 StatReload 会卡死（监听端口消失、Ctrl+C 失效）。uv trampoline 报错时用 `python -m uvicorn` 形式。

## 架构

### 模块注册（两端对称，核心扩展机制）

- 后端：功能在 `backend/app/modules/<name>/`（api.py + service.py + provider.py），`modules/__init__.py::_MODULES` 列表注册 `register_module(app)`。`main.py` 保持干净（app 创建 / 错误处理 / request-id 中间件），**绝不 import 具体模块**。
- 前端：`frontend/src/modules/<name>/` + `defineOpsModule({...})`，注册于 `src/modules/index.ts`；侧栏菜单与路由 `/console/site/:siteId/:moduleId` 由注册表生成。
- 模块：`sites, server, redis, mq, device, overview, audit, ssh, testconn, database`（最后为占位示例）。
- **新增模块 = 两端各加一个目录 + 注册表一行**，不改 main.py / 布局 / 路由。

### 不可协商的规则（PRD / 实践沉淀）

- **两种 Redis 永不混用**：平台 Redis（`OPS_REDIS_URL`，`core/redis.py` 单例池，存配置/缓存/锁/操作日志/采样）vs 被监控业务 Redis（redis 模块 provider 每次新建、用毕即关）。业务 provider 严禁复用平台客户端。
- **Adapter-first**：service 层不直接触碰 asyncssh/redis-py/httpx，只经模块 provider。
- **Server 只读**：SSH 命令固定白名单（provider 内声明），无用户输入命令面；Redis 是唯一可写资源（SCAN 只读、删除需倒计时确认、一切写操作记操作日志）。
- **并发三层限流**（`shared/concurrency.py`）：读路径 `ssh/8`；脚本/流式执行 `ssh_run/4` + **按主机 `/2`**（`get_host_semaphore`）——新增 SSH 触点必须挂信号量，否则多用户会在目标机上无限堆进程。MQ/Redis/Robot 各有全局信号量。
- **一切外呼**：超时 + 有界重试（`RETRYABLE_CODES` 之外不重试，如 AUTH_FAILED/REMOTE_KILL_FAILED）+ 单飞缓存（`core/cache.py`，失败写负哨兵防死机风暴）。错误统一 OpsError 信封，单资源故障渲染 Unknown 而非 500。
- **写路径验证远端结果**：如 zombie kill 用 `&& echo __KILL_OK__` 标记判定成败，失败原话抛回（oplog 记 FAILED）。
- **采样语义**：趋势样本由**页面轮询的真实拉取**驱动（无后台采样器），写时续期 2h TTL；删除站点连带清三种形态的采样 key（`ops:sample:server/{site}:*` / `mq:{site}:*` / `{site}:*`）。
- **操作日志**：上限 320 条（`core/oplog.py OPLOG_MAX`）；`target`=操作对象名、`resource`=模块/实例名（内部 id 进 params），约定见 `oplog.record` docstring。
- **i18n**：所有用户可见文案走 `src/i18n/index.ts`（zh+en 双语）与 `help.ts`；**文案里严禁字面花括号**（vue-i18n 占位符语法，会编译崩溃）——示例语法硬编码在模板里不过 $t。
- **前端 naive-ui**：显式具名 import（模板用了未 import 的组件 = 不可见元素，经典坑）；定时器三件套 = interval + `visibilitychange` 暂停 + `onBeforeUnmount` 清理（新增轮询视图必须齐全）；截断文本悬浮全文+复制统一用 `components/TipCopy.vue`。
- **前端构建版本号**：`MainLayout.vue` 的 build-stamp 格式 `bMMDD-HHMM`（中国本地时间），**每次前端改动必须更新**——用户靠它核对页面是否加载新代码。

### Device 字段映射要点

- 模板占位符：`{field}` 单字段、`{f1,f2}` 多字段（值逗号连接），整串无合法占位符时按字段名直取（`device/provider.py eval_value`；前端 `FieldMappingDialog rawValue` 同规则镜像）。
- 自定义展示字段存于资源配置 `custom_fields`（key `cf_xxxxx` 稳定、label_zh/label_en 双语、≤10）。
- 弹窗行布局为显式模式选择（绑定/模板二选一，保存只写所选），原始值/预览两列恒同屏。

## Testing

- 后端：`backend/tests/`（pytest + fakeredis），覆盖各模块 API、采样、缓存、僵尸分组、oplog 可读性、SSE 流式。
- 前端：`frontend` vitest（registry / site store / CountdownConfirm / ResourceTestButton / RedisView 回归）。
- 改动完成的门槛：`uv run pytest backend/tests -q` 与 `cd frontend && npx vitest run` 双绿；涉及轮询/SSH 的改动需真实环境冒烟。

## Gotchas

- `route.params.moduleId` **不存在**（路由按模块生成静态尾段）——当前模块从 path 尾段反查（`MainLayout.activeModule`），别再读那个幽灵参数。
- `.env` 含真实凭据，已 gitignore 绝不入库；对外交付用 `.env.example`。
- `layout/` 目录是用户本地截图，已 gitignore，不要提交。
