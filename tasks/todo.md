# Ops Console V1 任务清单

来源：`docs/prd-tech-design-v0.2.md` · 计划：`tasks/plan.md` · 生成：2026-09-21
完成一项勾一项。验证命令：后端 `uv run pytest`；前端 `cd frontend && npm run build && npx vitest run`。

---

## Phase 1 基础工程 + 模块注册框架

### Task 01: 仓库结构重组与依赖安装
**描述**：`main.py` 迁入 `backend/app/main.py`；根 pyproject 增加运行依赖（pydantic v2、redis-py、asyncssh、httpx、apscheduler、loguru）与 dev 依赖（pytest、pytest-asyncio、httpx）；脚手架 `frontend/`（Vite + Vue3 + TS + naive-ui + pinia + vue-router + axios + echarts，dev 加 vitest）。
**验收标准**：
- [x] `uv run uvicorn backend.app.main:app --reload` 访问 `/` 返回 Hello World
- [x] `cd frontend && npm run dev` 可打开页面，`npm run build` 通过
- [x] CLAUDE.md 的命令更新为新结构
**依赖**：无
**文件**：`backend/app/main.py`、`pyproject.toml`、`frontend/**`、`CLAUDE.md`
**规模**：M

### Task 02: 后端 core 基础设施
**描述**：`core/config.py`（OPS_REDIS_URL、超时组等环境变量）、`core/redis.py`（平台 Redis 单例，独占 `OPS_REDIS_URL`）、`core/cache.py`（短 TTL 缓存 + 短 TTL 锁请求合并）、`shared/errors.py`（统一错误包络 `{success, error_code, message, resource}`）、`shared/timeout.py`、`shared/concurrency.py`（每类资源信号量）。提供 `GET /api/health`。
**验收标准**：
- [x] `/api/health` 返回平台 Redis ping 结果
- [x] 单测：并发 10 次缓存未命中调用只产生 1 次下游访问（锁合并生效）
**依赖**：T01
**文件**：`backend/app/core/*`、`backend/app/shared/*`
**规模**：M

### Task 03: 后端模块注册机制
**描述**：`core/registry.py` + `modules/__init__.py` 的 `register_all(app)`；`main.py` 只负责 create app + register_all；加一个 demo 模块验证机制。
**验收标准**：
- [x] demo 模块路由经 `register_all` 挂载可访问
- [x] `main.py` 中无任何具体模块 import
**依赖**：T02
**文件**：`backend/app/core/registry.py`、`backend/app/modules/__init__.py`、`backend/app/main.py`
**规模**：S

### Task 04: 操作日志 core
**描述**：`core/oplog.py`：`record(site, resource, operation, target, params, result, error)` → `LPUSH ops:oplog` + `LTRIM 0 999`；`read_recent(n)`、`read_page(page, size)`。无用户字段。
**验收标准**：
- [x] 单测：写入超 1000 条后仅保留最近 1000
- [x] 单测：`read_recent(20)` 返回最近 20 条
**依赖**：T02
**文件**：`backend/app/core/oplog.py`、`backend/tests/test_oplog.py`
**规模**：S

### Task 05: 前端骨架 + 模块注册机制
**描述**：`api/` axios 封装（统一错误处理）、`layouts/`（侧边栏/顶栏/Site 切换器占位）、`stores/site.ts`（currentSiteId/currentSite）、`modules/registry.ts`（`defineOpsModule` + OpsModule 类型）、router 遍历 registry 生成 `/console/site/:siteId/:moduleId`；一个 demo 模块端到端。
**验收标准**：
- [x] 新增 demo 模块 = 新增目录 + 一行注册，菜单与路由自动出现（不改 layout/router）
- [x] vitest：registry 排序/注册单测通过
**依赖**：T01（可与 T02-T04 并行）
**文件**：`frontend/src/{api,layouts,stores,router,modules}/**`
**规模**：M

### ✅ Checkpoint 1（T01-T05）
- [x] 前后端 dev server 可启动，pytest 全绿
- [x] demo 模块：前端一行注册出菜单/路由，后端一行注册出路由
- [x] `main.py` 干净（仅 app + register_all）

---

## Phase 2 Site 管理

### Task 06: Sites CRUD API
**描述**：PRD §5/§6：`ops:site:{id}` Hash；字段 id/name/description/enabled/created_at/updated_at；密码不回显（返回空/掩码）、提交留空 = 不修改。路由按 §18 站点部分。
**验收标准**：
- [x] GET 列表/详情响应无明文密码；PUT 密码留空不覆盖原值（T07 落地）
- [x] API 测试：增删改查 + 启用禁用全通过
**依赖**：T03
**文件**：`backend/app/modules/sites/{api,service}.py`
**规模**：M

### Task 07: 站点资源配置 CRUD
**描述**：四类资源（servers/redis_instances/mq_instances/robots）在站点下的增删改查，统一配置结构（id/name/host/port/username/password/.../enabled），密码规则同 T06，必填项校验。
**验收标准**：
- [x] 四类资源 CRUD 路由可用，缺必填字段返回 422
- [x] 密码回显规则与 T06 一致
**依赖**：T06
**文件**：`backend/app/modules/sites/*`
**规模**：M

### Task 08: 配置导出 / 导入
**描述**：`POST /api/sites/export`（全量 JSON）、`POST /api/sites/import`（覆盖式导入），写 oplog（SITE_CONFIG_CHANGED）。
**验收标准**：
- [x] 单测：export → 清空 → import 后站点与资源一致
**依赖**：T07
**文件**：`backend/app/modules/sites/*`
**规模**：S

### Task 09: 前端站点管理与 Site 切换
**描述**：站点列表/新建/编辑/启停页；四类资源配置表单（密码输入留空提示"不修改"）；顶栏 Site 切换器写入 store，切换后停留在当前模块（路由参数变化，模块 watch 响应）。
**验收标准**：
- [x] UI 完成一次建站 + 配资源 + 编辑（密码留空保存后原密码仍生效；API 流已对真实后端验证，存储级断言见 pytest）
- [x] 切换站点 URL 与页面数据随之刷新
**依赖**：T05、T06、T07（API 契约）
**文件**：`frontend/src/modules/sites/**`、`frontend/src/layouts/**`
**规模**：M

### Task 10: 连接测试框架
**描述**：`POST /api/test-connection` Body `{type, config}`，按 type 分发到各模块 provider 的 `test(config)`；响应 `{success, latency_ms, message}`；前端通用 `ResourceTestButton.vue`（loading / 结果 / 错误信息），表单内（未保存配置）与列表（已存配置含密码）两处可用。
**验收标准**：
- [x] 未知 type 返回统一错误包络
- [x] ResourceTestButton 单测：success / failure 两态渲染
**依赖**：T03、T05
**文件**：`backend/app/shared/`（或 core）测试分发器、`frontend/src/components/ResourceTestButton.vue`
**规模**：S

### ✅ Checkpoint 2（T06-T10）
- [x] UI 建站 + 配资源 + 导出导入 roundtrip 通过（API 流实测 + pytest）
- [x] pytest 全绿（20 passed）

---

## Phase 3-4 Server（只读诊断）

### Task 11: SSH Provider（白名单 + 解析器）
**描述**：`SSHServerMetricsProvider`（asyncssh，按需连接查完即关）：一次会话聚合执行固定白名单命令（top -bn1 / uptime / free -m / df -h / df -i / /proc/net/dev / ps），解析为结构化 metrics + processes；白名单为模块常量，API 层不可传入任何命令。
**验收标准**：
- [x] 解析器单测：固定样本输出 → 全字段正确（含字段缺失 → None）
- [x] 单测：provider 只会执行白名单集合内的命令
**依赖**：T02
**文件**：`backend/app/modules/server/provider.py`、`backend/tests/test_ssh_parser.py`
**规模**：M

### Task 12: Server API + 缓存合并
**描述**：`GET servers/{id}/metrics|processes`（5s 缓存 + Redis 锁合并 + SSH 超时）+ provider `test()` 接入 `/api/test-connection`（连接 + 认证 + 白名单命令可执行）。
**验收标准**：
- [x] 单测：并发请求同一 server 仅一次 SSH 调用
- [x] SSH 失败返回统一错误包络，接口不 500
**依赖**：T07、T10、T11
**文件**：`backend/app/modules/server/{api,service}.py`
**规模**：M

### Task 13: 诊断引擎
**描述**：阈值规则 CPU ≥80 WARNING/≥90 CRITICAL、Memory ≥80/≥90、Disk ≥85/≥95；Load 结合 core 数判断；输出 `{status, issues[]}`；全局默认阈值常量。
**验收标准**：
- [x] 单测覆盖每条规则各档位与边界值（79/80/89/90…）
**依赖**：T11
**文件**：`backend/app/modules/server/diagnosis.py`、`backend/tests/test_diagnosis.py`
**规模**：S

### Task 14: 阈值覆盖
**描述**：阈值按 资源级 > 站点级 > 全局默认 三层合并，覆盖值存平台 Redis，随资源配置 API 读写。
**验收标准**：
- [x] 单测：三层合并优先级正确，缺层回退
**依赖**：T13
**文件**：`backend/app/modules/server/`、`backend/app/modules/sites/`
**规模**：S

### Task 15: 前端 Server 模块
**描述**：`defineOpsModule` 注册；指标卡片（CPU/Mem/Disk/Load/Network）、Top Process 表、诊断 issues 列表、StatusBadge、ResourceTestButton、手动刷新；loading / Unknown / 错误态。页面无任何写入口。
**验收标准**：
- [x] 查询失败显示 Unknown 不白屏
- [x] 页面上无任何命令输入或操作按钮
**依赖**：T05、T12、T13、T14
**文件**：`frontend/src/modules/server/**`
**规模**：M

### ✅ Checkpoint 3（T11-T15）
- [x] 对真实/模拟 Linux 出全量指标 + 诊断色（真机 10.102.129.21 实测，站点级阈值覆盖生效）
- [x] Server 页面纯只读（验收 8）

---

## Phase 5-6 Redis（唯一可写资源）

### Task 16: 目标 Redis Provider + Info + 测试
**描述**：按站点配置动态建连（与平台 Redis 不同连接对象，严禁混用）；`GET .../redis/{id}/info`（§11.1 字段）；provider `test()`（PING + INFO，返回版本）。
**验收标准**：
- [x] 单测/代码审查：平台与业务 Redis 客户端来自不同工厂，无共享连接
- [x] info 字段覆盖 §11.1 列表
**依赖**：T07、T10
**文件**：`backend/app/modules/redis/provider.py`
**规模**：M

### Task 17: SCAN 浏览 + Key 详情
**描述**：`GET .../keys?db&pattern&cursor&count&type`（SCAN cursor MATCH COUNT，类型过滤在客户端 TYPE 过滤或 SCAN 后过滤）；`GET .../key?db&key` 返回 5 类型的 value + TTL + memory usage。禁 KEYS。
**验收标准**：
- [x] 单测：游标翻页（Load More 语义）正确
- [x] `grep -r "keys(" backend/app/modules/redis` 无 SCAN 之外的用法（SCAN 仅经 provider.scan）
**依赖**：T16
**文件**：`backend/app/modules/redis/{api,service}.py`
**规模**：M

### Task 18: 操作 API + 危险命令拒绝 + oplog
**描述**：`POST .../operations` `{op: set|delete|expire, db, key, ...}`，按类型校验 value 结构；命令白名单实现（SCAN/INFO/GET 系/SET 系/DEL/EXPIRE/TTL/TYPE/PTTL/MEMORY USAGE），FLUSHDB/FLUSHALL/CONFIG/SHUTDOWN/SCRIPT FLUSH/EVAL 在实现层不可达；每次写操作记 oplog。
**验收标准**：
- [x] 单测穷举危险命令 → 全部 4xx 拒绝
- [x] 单测：set/delete/expire 各产生一条 oplog
- [x] value 参数非法 → 4xx，不触达 Redis
**依赖**：T04、T17
**文件**：`backend/app/modules/redis/{api,service}.py`
**规模**：M

### Task 19: 前端 Redis 浏览器
**描述**：DB 切换、Pattern + Type 搜索、SCAN Load More、Key 列表（类型徽标/TTL）、Key 详情只读视图（5 类型格式化展示，STRING 尝试 JSON 美化）、ResourceTestButton。
**验收标准**：
- [x] 大 key 集（>1000）下 Load More 流畅不卡死（SCAN count=100 分页追加，交互验证留 T32 E2E）
**依赖**：T05、T17
**文件**：`frontend/src/modules/redis/**`
**规模**：M

### Task 20: 前端 Redis 编辑与删除
**描述**：类型化编辑（STRING 文本域 / HASH 表格或 JSON / LIST、SET JSON 数组 / ZSET score+member JSON）、TTL 输入框（设置/清除）、保存确认对话框（显示 key 与变更摘要）、`CountdownConfirm.vue` 通用组件（删除 5 秒倒计时禁点）。
**验收标准**：
- [x] 每种类型完成一次编辑→保存→重查一致（pytest 5 类型 + 真机 zset/string 冒烟）
- [ ] 删除按钮 5 秒内不可点，倒计时结束可删（vitest 已断言；浏览器交互留 T32）
**依赖**：T18、T19
**文件**：`frontend/src/modules/redis/**`、`frontend/src/components/CountdownConfirm.vue`
**规模**：M

### ✅ Checkpoint 4（T16-T20）
- [ ] SCAN 无 KEYS（grep 验证，验收 9）
- [ ] 编辑保存、倒计时删除、危险命令拒绝、oplog 全部可演示（验收 10/11/12/13）

---

## Phase 7-8 MQ / Robot

### Task 21: ArtemisProvider（Jolokia）
**描述**：httpx 访问 Jolokia / Management API（basic 认证）：broker overview、JVM、queues、addresses 查询；`test()`（API 可达 + 认证）。解析用现场样本 JSON 做单测。
**验收标准**：
- [x] 解析器单测：样本 Jolokia 响应 → §9.1-9.4 字段
- [x] 超时/连接失败 → 统一错误包络
**依赖**：T07、T10
**文件**：`backend/app/modules/mq/provider.py`、`backend/tests/test_mq_provider.py`
**规模**：M

### Task 22: MQ API + 诊断 + backlog 趋势（引入 APScheduler）
**描述**：`GET mq/{id}/overview|queues|addresses`（5s 缓存）；诊断：backlog 阈值、consumers=0、增长检测；APScheduler 周期采样 queue messageCount 写 Redis（`ops:sample:mq:{id}:{queue}` 短期保留）供趋势对比（Current vs 5min ago）。
**验收标准**：
- [x] 单测：诊断规则各分支
- [x] 单测：采样写入与 5 分钟前值读取
- [x] `ponytail:` 注释标注单实例假设
**依赖**：T21
**文件**：`backend/app/modules/mq/{api,service}.py`、`backend/app/core/scheduler.py`
**规模**：M

### Task 23: 前端 MQ 模块
**描述**：Broker/JVM 卡片、Queue 表（count/consumer/delivering + TrendSpark 趋势）、Address 表、诊断徽标、ResourceTestButton。
**验收标准**：
- [x] backlog 超阈值行有 WARNING/CRITICAL 标识
**依赖**：T05、T22
**文件**：`frontend/src/modules/mq/**`、`frontend/src/components/TrendSpark.vue`
**规模**：M

### Task 24: RobotProvider + API
**描述**：`HttpRobotProvider`（httpx，按配置 base_url/认证）：`get_robot_list/get_robot_status/get_robot_detail` 映射为统一结构（ID/Name/Status/Battery/Station/Task/LastUpdate）；API：`GET robots`、`GET robots/{id}`；`test()`（API 可达）。
**验收标准**：
- [x] provider 字段映射单测（真实样例 JSON 做样本）
**依赖**：T07、T10
**文件**：`backend/app/modules/robot/**`
**规模**：M

### Task 25: 前端 Robot 模块
**描述**：列表页（§12.1 字段 + StatusBadge）+ 详情页（Basic Info/Status/Battery/Position/Task/Error）+ ResourceTestButton。
**验收标准**：
- [x] 列表 → 详情跳转与字段渲染正常
**依赖**：T05、T24
**文件**：`frontend/src/modules/robot/**`
**规模**：S

### ✅ Checkpoint 5（T21-T25）
- [x] MQ 与 Robot 页面在真实/模拟环境可查看（MQ 真机 2.44.0 实测；Robot 真实 API 待现场信息，stub 已验）
- [x] 连接测试四类资源全部可用（验收 5）

---

## Phase 9 Overview

### Task 26: 后台健康检查 job
**描述**：APScheduler 30 秒轻量检查（Server CPU/Mem/Disk、MQ 连接/backlog、Redis 连接/内存、Robot 可达性），结果写缓存供 Overview 使用；详细数据仍按需查询。
**验收标准**：
- [ ] 单测：单轮检查聚合各模块轻量结果并写缓存 key
- [ ] 单个资源失败不影响其他资源检查
**依赖**：T22（scheduler）、T12/T16/T21/T24
**文件**：`backend/app/core/scheduler.py`、`backend/app/modules/overview/service.py`
**规模**：M

### Task 27: Overview API
**描述**：`GET /api/sites/{id}/overview`：Overall（HEALTHY/WARNING/CRITICAL）、各资源类型计数与状态、异常摘要 issues[]、最近 20 条 oplog。
**验收标准**：
- [ ] 单测：任一资源 CRITICAL → Overall CRITICAL；仅 WARNING → WARNING
**依赖**：T26、T04
**文件**：`backend/app/modules/overview/{api,service}.py`
**规模**：M

### Task 28: 前端 Overview 模块
**描述**：站点健康瓦片（四类资源计数 + 状态色）、异常摘要列表（可点击跳转对应模块）、最近操作卡片、站点无资源空态。
**验收标准**：
- [ ] 异常摘要点击跳转到对应模块页面
**依赖**：T05、T27
**文件**：`frontend/src/modules/overview/**`
**规模**：M

---

## Phase 10 操作日志页 + 稳定性

### Task 29: Audit API + 前端日志页
**描述**：`GET /api/audit?page&size`（分页读 ops:oplog 全量 ≤1000）；前端独立操作日志页（时间/站点/资源/操作/目标/结果，表格分页）。
**验收标准**：
- [ ] 分页边界（空/末页）正常
**依赖**：T04、T05
**文件**：`backend/app/modules/audit/api.py`、`frontend/src/modules/audit/**`
**规模**：S

### Task 30: 稳定性收尾
**描述**：全仓审计——所有外部调用有 timeout（§26 数值）、Connection Error 最多重试 1-2 次、SSH/MQ/Robot 信号量并发上限生效、所有对外错误走统一包络、前端 Unknown/超时态全覆盖。
**验收标准**：
- [ ] grep/审查清单逐项过（timeout、retry、信号量、错误包络）
- [ ] 人为断开某资源，平台其余功能不受影响
**依赖**：T12、T16-T18、T21-T24
**文件**：`backend/app/**`（分散小改）
**规模**：M

---

## Phase 11 部署

### Task 31: Docker Compose
**描述**：backend Dockerfile（uv 安装 + 运行）、ops-nginx（托管 frontend dist + `/api` proxy_pass backend:8000）、`compose.yaml` + `.env`（宿主机端口默认 8090、OPS_REDIS_URL、超时变量、OPS_LOG_LEVEL）、volume backend-logs。不构建 Redis，不占用 80。
**验收标准**：
- [ ] `docker compose up -d` 一条命令启动，`http://<host>:8090` 可用且 `/api` 反代正常（验收 1/2）
- [ ] 与现有 nginx（80）互不影响
**依赖**：T01-T30（功能完备后）
**文件**：`backend/Dockerfile`、`deploy/nginx.conf`、`compose.yaml`、`.env.example`
**规模**：M

---

## Phase 12 测试与验收

### Task 32: 测试补全 + E2E 主路径
**描述**：对照 PRD §32 补齐单元/API 测试缺口；E2E 主路径：选 Site → Overview → Server → Redis 搜索 → 编辑 Key 保存 → 倒计时删除 → 连接测试 → MQ → Robot。
**验收标准**：
- [ ] E2E 全路径通过一次录屏/截图留证
- [ ] pytest + vitest 全绿
**依赖**：T31
**文件**：`backend/tests/**`、`frontend/tests 或 e2e/**`
**规模**：M

### Task 33: 扩展性验证 demo（验收 17/18）
**描述**：新增后端 `modules/database/`（返回假指标的一个 GET 路由）+ 前端 `modules/database/`（一个只读页面），各自仅"新增目录 + 一行注册"，不改 main.py / layout / router / store。
**验收标准**：
- [ ] git diff 显示核心文件零改动（仅 modules 列表各加一行）
- [ ] demo 模块页面与菜单正常出现
**依赖**：T03、T05
**文件**：`backend/app/modules/database/**`、`frontend/src/modules/database/**`
**规模**：S

### ✅ Checkpoint 6（完成）
- [ ] PRD §33 验收标准 1-18 逐条核对通过
- [ ] V1 完成
