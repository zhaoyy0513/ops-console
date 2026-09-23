# 内部服务器运维诊断平台

## PRD + 技术设计文档

> 文档版本：v0.2\
> 文档状态：基于 v0.1 与需求方反馈修订\
> 目标：作为后续 AI 辅助设计、开发、测试的基准文档\
> 部署方式：Docker Compose（仅 backend，复用现有 nginx / Redis 容器）\
> 使用范围：公司内部运维 / 开发 / 测试人员

------------------------------------------------------------------------

# 0. v0.1 → v0.2 变更摘要

| # | 变更 | 说明 |
|---|------|------|
| 1 | 移除用户体系 | 无登录、无 RBAC、无用户概念，系统不做任何用户相关功能 |
| 2 | 简化操作日志 | 只记录操作本身（时间 / 站点 / 资源 / 操作 / 目标 / 参数 / 结果），不含用户信息 |
| 3 | 移除 Secret 管理 | 不做加密存储体系；密码仅在提交时写入，查询接口不回显 |
| 4 | 简化部署 | Compose 包含 backend + 平台自有 nginx（独立端口，不与现有 nginx 冲突）；Redis 复用现有容器；移除 ops-redis 容器与配置持久化要求，提供配置导出 / 导入 JSON 作为轻量备份 |
| 5 | 收敛安全要求 | 不做认证 / 授权 / 限流；平台不向用户提供任何 SSH 操作入口，服务器信息只读展示；Redis 是唯一允许写操作的外部资源 |
| 6 | 新增连接测试 | Server / Redis / MQ / Robot 配置后均可一键测试连通性（支持保存前测试） |
| 7 | Redis 编辑体验对齐 RedisDesktop | value 以文本 / JSON 形式直接编辑保存；删除带 5 秒倒计时二次确认 |
| 8 | 强化模块化扩展 | 前后端均采用模块注册机制，后续新增数据库等监控模块只新增目录 + 注册，不改动核心代码 |

------------------------------------------------------------------------

# 1. 项目概述

## 1.1 项目名称

内部服务器运维诊断平台（Internal Server Operations & Diagnostics
Platform）

以下简称：**Ops Console**

## 1.2 项目定位

本系统不是传统意义上的大规模监控平台，而是一个：

> **轻量、低资源、以快速定位问题为核心的内部运维诊断平台。**

主要解决以下问题：

-   公司存在多个站点、服务器和中间件；
-   当 CPU、内存、磁盘、MQ、Redis 等出现异常时，需要登录不同服务器逐一排查；
-   运维人员需要重复输入服务器、Redis、MQ 等连接信息；
-   不同系统的信息分散，无法从站点维度快速查看；
-   希望通过一个统一 Web 平台快速判断"哪里异常、为什么异常"。

系统的核心目标不是持续采集海量指标，而是：

> **选择站点 → 快速查看整体健康状态 → 定位异常资源 → 查看详细诊断信息 →
> 必要时对 Redis 执行受保护的运维操作。**

------------------------------------------------------------------------

# 2. 核心设计原则

## 2.1 Site Context First

站点是整个系统的核心上下文。

用户选择一个站点后：

``` text
Site
 ├── Overview
 ├── Server
 ├── Redis
 ├── ActiveMQ
 └── Robot
```

所有模块自动继承当前站点配置，用户不需要重复输入 IP、账号、密码等信息。

## 2.2 Diagnose > Monitor

系统不仅展示：

``` text
CPU = 92%
```

还应该尽可能进一步给出：

``` text
CPU = 92% WARNING

Top Process:
java / PID 1234 / CPU 87%

可能原因：
Java 进程 CPU 占用异常
```

系统的价值在于：

> **帮助用户快速定位问题，而不是单纯展示数字。**

## 2.3 On-demand First

默认不做大规模持续轮询。

采用：

``` text
用户查看
    ↓
按需查询
    ↓
短时间缓存
    ↓
返回结果
```

对于首页健康摘要，可以进行低频后台检查（30 秒级）。

## 2.4 Short Cache

对高成本查询使用短 TTL 缓存：

``` text
Server Metrics      5~10 秒
MQ Overview         5~10 秒
Redis Info          5~10 秒
Robot Status        5~10 秒
```

避免多个用户同时打开同一页面时重复连接外部系统。

## 2.5 Adapter First

外部系统全部通过 Adapter / Provider 隔离：

``` text
Business Service
       ↓
Provider / Adapter
       ↓
SSH / Redis / Artemis / HTTP
```

业务层不能直接依赖具体第三方协议实现。

## 2.6 Module Registry

前后端均采用**模块注册式**设计：

``` text
核心框架（layout / router / site context / cache / registry）
       ↓
功能模块（overview / server / redis / mq / robot / ...）
```

后续新增模块（如数据库监控、Docker 监控等）：

> **只新增一个模块目录 + 一行注册，不修改核心框架代码。**

这是 v0.2 的重点设计要求，前后端同标准执行。

## 2.7 Simple but Extensible

第一版避免：

-   Kafka
-   Celery
-   WebSocket
-   Prometheus
-   Grafana
-   Elasticsearch
-   大规模时序数据库

但架构需要给未来扩展留下接口。

------------------------------------------------------------------------

# 3. 使用场景

系统完全内部使用，**无用户体系**：

-   无登录；
-   无角色权限；
-   打开即用。

典型使用者与关注点：

### 运维人员

-   服务器 / MQ / Redis / Robot 健康状态
-   异常诊断
-   Redis Key 运维操作

### 开发人员

-   服务所在服务器状态
-   Redis Key、MQ Queue / Topic
-   Robot 状态、进程状态

### 管理人员

-   当前站点整体健康情况
-   异常资源数量

------------------------------------------------------------------------

# 4. 核心业务模型

系统核心对象：

``` text
Site
 ├── Server
 ├── Redis
 ├── ActiveMQ
 └── Robot
```

未来可以扩展（通过模块注册机制）：

``` text
Site
 ├── Docker
 ├── PostgreSQL
 ├── MySQL
 ├── PLC
 ├── HTTP Service
 └── ...
```

------------------------------------------------------------------------

# 5. Site 设计

## 5.1 Site 定义

Site 表示一个业务站点或部署环境。

例如：

``` text
深圳测试站
上海生产站
北京测试站
```

一个 Site 可以包含多个同类资源（多台服务器、多个 Redis 等）。

## 5.2 Site 配置

Site 本身：

``` text
id
name
description
enabled
created_at
updated_at
```

资源：

``` text
servers        # SSH 连接配置
redis_instances
mq_instances
robots         # HTTP API 配置
```

资源通用配置结构（以 Redis 为例）：

``` json
{
  "id": "redis-01",
  "name": "redis-01",
  "type": "redis",
  "host": "10.10.1.20",
  "port": 6379,
  "username": "",
  "password": "",
  "db": 0,
  "enabled": true
}
```

说明：

-   密码允许为空（很多站点默认无密码）；
-   密码字段在查询接口中**不回显**（返回空或掩码），提交时留空表示"不修改"。

------------------------------------------------------------------------

# 6. 配置存储

## 6.1 存储方案

平台复用**现有 Redis 容器**作为配置存储 + 缓存，通过环境变量接入：

``` text
OPS_REDIS_URL=redis://existing-redis:6379/5
```

建议为平台分配独立 DB（如 db 5），与现有业务 Key 逻辑隔离。

## 6.2 Key 结构

推荐使用 Hash，不散落大量 Key：

``` text
ops:site:{site_id}                  # Site 基本信息 Hash
ops:site:{site_id}:servers          # server_id -> JSON
ops:site:{site_id}:redis            # redis_id -> JSON
ops:site:{site_id}:mq               # mq_id -> JSON
ops:site:{site_id}:robots           # robot_id -> JSON
```

## 6.3 不做持久化要求

平台**不要求**配置持久化：

-   不新建 ops-redis 容器；
-   不配置持久化 Volume；
-   现有 Redis 重启导致配置丢失属于可接受风险。

作为轻量兜底，V1 提供：

``` text
POST /api/sites/export              # 导出全部 Site 配置为 JSON
POST /api/sites/import              # 从 JSON 导入
```

用户可定期手动导出备份。

------------------------------------------------------------------------

# 7. Overview 首页

首页是系统核心入口。

用户选择 Site 后看到：

``` text
深圳测试站

Overall Status
    HEALTHY / WARNING / CRITICAL

Server
    3
    Warning: 1

Redis
    2
    Healthy

ActiveMQ
    2
    Warning: 1

Robot
    18
    Healthy
```

## 7.1 异常摘要

例如：

``` text
WARNING

Server-02
Memory usage 87%

CRITICAL

Server-03
/data disk usage 94%

WARNING

MQ-01
Queue robot.task backlog 12,381
```

## 7.2 最近操作

显示最近的关键操作（来自操作日志，无用户维度），展示**最近 20 条**：

``` text
13:42 Redis DELETE robot:001
13:38 Site configuration changed
13:21 Redis SET robot:002
```

完整操作日志见第 17 节（保留最近 1000 条）。

------------------------------------------------------------------------

# 8. Server 模块

## 8.1 查询方式

第一版通过 SSH 连接 Linux Server。

支持：

``` text
IP
Domain
Hostname
```

认证支持：

``` text
Username + Password
Username + SSH Private Key
```

## 8.2 只读原则

> **平台不向用户提供任何 SSH 操作入口。**

-   服务器相关功能全部为**只读展示**；
-   不提供终端、不提供任意命令执行、不提供文件操作；
-   后端仅执行**内置诊断命令白名单**（详见第 10 节）。

## 8.3 Server Metrics

### CPU

``` text
CPU Usage
CPU Core
Load 1m
Load 5m
Load 15m
IO Wait
```

### Memory

``` text
Total
Used
Available
Cached
Swap
Swap Used
```

### Disk

``` text
Mount Point
Total
Used
Available
Usage %
Inode Usage
```

重点关注：

``` text
/
/data
/var
```

### Network

``` text
RX
TX
Errors
Dropped
```

### Process

Top Process：

``` text
PID
Process
CPU %
Memory %
```

## 8.4 查询原则

禁止：

``` text
CPU → 建立 SSH → 查询 → 关闭
Memory → 建立 SSH → 查询 → 关闭
Disk → 建立 SSH → 查询 → 关闭
```

推荐：

``` text
建立一次 SSH
      ↓
执行聚合查询（一次远程命令返回结构化结果）
      ↓
CPU / Memory / Disk / Load / Network
      ↓
关闭
```

## 8.5 Server Provider 抽象

``` python
class ServerMetricsProvider:
    async def get_metrics(...)
    async def get_processes(...)
    async def get_disk(...)
```

第一版：

``` text
SSHServerMetricsProvider
```

未来：

``` text
PrometheusServerMetricsProvider
```

这样未来引入 Prometheus 不需要修改业务层。

## 8.6 诊断规则

示例：

``` text
CPU >= 80%       WARNING
CPU >= 90%       CRITICAL

Memory >= 80%    WARNING
Memory >= 90%    CRITICAL

Disk >= 85%      WARNING
Disk >= 95%      CRITICAL
```

Load Average 不直接使用固定阈值，应结合 CPU Core 数量判断。

诊断输出：

``` json
{
  "status": "WARNING",
  "issues": [
    {
      "type": "CPU_HIGH",
      "severity": "WARNING",
      "value": 92,
      "threshold": 80,
      "message": "CPU usage is high"
    }
  ]
}
```

阈值支持按站点 / 按服务器覆盖，全局默认值兜底。

------------------------------------------------------------------------

# 9. ActiveMQ Artemis 模块

目标版本：

``` text
Artemis 2.19
```

推荐优先通过 Artemis Management API / Jolokia 获取管理数据。

## 9.1 Broker Overview

显示：

``` text
Status
Version
Uptime
Connections
Sessions
Consumers
Producers
Messages
```

## 9.2 JVM

显示：

``` text
Heap Used
Heap Max
Non Heap
Threads
GC
```

## 9.3 Queue

显示：

``` text
Queue Name
Message Count
Consumer Count
Delivering Count
Messages Added
Messages Acknowledged
```

## 9.4 Address / Topic

显示：

``` text
Address
Message Count
Consumer Count
Producer Count
```

## 9.5 MQ 诊断

重点检测：

``` text
Queue backlog
Consumers = 0
Messages 持续增长
Delivering 数量异常
Broker CPU
JVM Memory
```

## 9.6 Queue 堆积趋势

不只显示当前值，还比较短时间前的值：

``` text
Current:     12381
5 min ago:   2341
Growth:      +10040  → WARNING
```

第一版不建时序数据库，使用 Redis 保存短期采样数据。

------------------------------------------------------------------------

# 10. SSH 诊断实现（后端内部细节）

> 本节描述的是**后端内部实现方式，不是面向用户的功能**。

SSH 查询对用户完全透明：

``` text
前端                                后端
────────                    ────────────────────────────
点击"查询指标"        →      读取站点配置中的 SSH 连接信息
loading 转圈                  建立一次 SSH 连接（按需，查完即关）
loading 转圈                  执行内置只读诊断命令（固定集合）
loading 转圈                  解析 + 阈值诊断
展示结果 / Unknown     ←      返回结构化 JSON
```

要点：

-   前端**没有任何命令输入入口**，也完全不感知后端执行了什么命令；
-   后端内部维护一组固定的只读诊断命令，属于实现细节：

``` text
CPU / Load        top -bn1 / uptime / /proc/stat
Memory            free -m / /proc/meminfo
Disk              df -h / df -i
Network           /proc/net/dev
Process           ps / top -bn1
```

-   前端只需要做好：loading 状态、超时提示、错误展示（Unknown）；
-   API 层面只有：

``` text
GET .../servers/{id}/metrics
GET .../servers/{id}/processes
```

前端无法传递任何自定义命令内容。

明确不提供：

``` text
Execute arbitrary shell command
文件上传 / 下载
终端交互
```

------------------------------------------------------------------------

# 11. Redis 模块

Redis 模块既可以查询被监控 Redis，也可以执行受控操作。

> **Redis 是平台中唯一允许写操作的外部资源。**

## 11.1 Redis Overview

显示：

``` text
Status
Version
Memory Used
Memory Peak
Memory Fragmentation
Connected Clients
Commands/sec
Hit Rate
Evicted Keys
Expired Keys
```

## 11.2 DB Browser

支持：

``` text
DB 0
DB 1
DB 2
...
```

查询使用：

``` text
SCAN
```

禁止使用：

``` text
KEYS *
```

## 11.3 Key Search

支持：

``` text
Pattern（如 robot:*）
Type 过滤
分页（SCAN cursor MATCH ... COUNT 100）
Load More
```

避免一次性加载大量 Key。

## 11.4 Key Detail 与编辑（参考 RedisDesktop）

支持类型：

``` text
STRING
HASH
LIST
SET
ZSET
```

显示：

``` text
Key
Type
TTL
Memory Usage
Value
```

编辑体验对齐 RedisDesktop：

``` text
STRING  → 文本域直接编辑（尝试 JSON 格式化展示）
HASH    → 表格或 JSON 形式编辑 field/value
LIST    → JSON 数组形式编辑
SET     → JSON 数组形式编辑
ZSET    → JSON（score + member）形式编辑
TTL     → 单独的 TTL 输入框，可设置 / 清除
```

保存流程：

``` text
编辑 value
    ↓
点击 Save
    ↓
确认对话框（显示 key 与变更摘要）
    ↓
写入并记录操作日志
```

## 11.5 操作保护

写操作（SET / DELETE / EXPIRE / 修改各类型 Value）需要确认。

**删除**使用带倒计时的二次确认：

``` text
You are about to delete:

robot:001

This operation cannot be undone.

Please wait 5 seconds...

[ Delete ]        ← 按钮 5 秒内不可点击
```

注意：

> **倒计时只是 UI 防误操作机制，不作为后端安全机制。**

## 11.6 危险命令

以下命令第一版**默认禁止**（前后端都不提供入口）：

``` text
FLUSHDB
FLUSHALL
CONFIG
SHUTDOWN
SCRIPT FLUSH
EVAL
```

------------------------------------------------------------------------

# 12. Robot 模块

Robot 通过 HTTP API 查询。

第一版定义统一接口：

``` text
get_robot_list()
get_robot_status()
get_robot_detail()
```

业务层不直接依赖具体 Robot API。

## 12.1 Robot 页面

列表：

``` text
Robot ID
Name
Status
Battery
Current Station
Last Update
```

详情：

``` text
Basic Information
Status
Battery
Position
Error
```

------------------------------------------------------------------------

# 13. 连接测试

**所有外部资源配置后，必须可以一键测试连通性。**

## 13.1 测试入口

前端两处：

1.  **配置表单内**：填写完连接信息后，点击 `Test Connection`，无需先保存；
2.  **资源列表 / 详情页**：对已保存资源点击 `Test`，使用存储的完整配置（含密码）测试。

## 13.2 测试内容

``` text
Server (SSH)   连接成功 + 认证成功 + 可执行白名单命令
Redis          连接成功 + 认证成功（PING + INFO）
MQ             Jolokia / Management API 可访问 + 认证成功
Robot          HTTP API 可访问
```

## 13.3 测试结果

``` json
{
  "success": true,
  "latency_ms": 42,
  "message": "Connected, Redis 7.2.4"
}
```

失败时给出可定位的错误：

``` json
{
  "success": false,
  "latency_ms": 3002,
  "message": "Connection timed out after 3s"
}
```

------------------------------------------------------------------------

# 14. Cache 设计

平台使用现有 Redis（独立 DB）负责缓存：

``` text
ops:cache:server:{server_id}:metrics      TTL 5s
ops:cache:mq:{mq_id}:overview             TTL 5s
ops:cache:redis:{redis_id}:info           TTL 5s
ops:cache:robot:{robot_id}:status         TTL 5s
```

------------------------------------------------------------------------

# 15. 请求合并

多个用户同时请求：

``` text
Server CPU
```

不应该产生多个 SSH 查询。

流程：

``` text
Request
   ↓
Cache
   ↓
Hit → Return
   ↓
Miss
   ↓
Lock（Redis 短 TTL 锁）
   ↓
SSH Query
   ↓
Cache
   ↓
Return
```

------------------------------------------------------------------------

# 16. 后台健康检查

后台只做轻量检查。

推荐频率：

``` text
30 秒
```

检查：

``` text
Server CPU / Memory / Disk
MQ Connection / Backlog
Redis Connection / Memory
Robot API 可达性
```

详细信息：

``` text
按需查询
```

## 16.1 Scheduler

可以使用：

``` text
APScheduler
```

职责：

``` text
健康检查
短期指标采样（如 Queue backlog 趋势）
缓存刷新
```

不要让 Scheduler 负责所有业务逻辑。

## 16.2 不采用长连接

第一版不使用：

``` text
长连接 SSH
WebSocket
持续 MQ Connection
持续 Redis Connection
```

除非后续真实需求证明必要。

------------------------------------------------------------------------

# 17. 操作日志

所有有副作用的操作必须记录。

**无用户维度**，记录：

``` text
Time
Site
Resource
Operation
Target
Parameters
Result
Error
```

例如：

``` text
2026-09-21 13:42
Site: shenzhen-test
Resource: redis-01
Operation: DELETE_KEY
Target: robot:001
Result: SUCCESS
```

``` text
2026-09-21 13:38
Site: shenzhen-test
Resource: site-config
Operation: SITE_CONFIG_CHANGED
Result: SUCCESS
```

## 17.1 存储方案

存储在**平台 Redis**（即 `OPS_REDIS_URL` 指向的 Redis，使用平台独立 DB），
使用 List 结构：

``` text
LPUSH ops:oplog <json>
LTRIM ops:oplog 0 999
```

保留策略：

``` text
总量：只保留最近 1000 条（LPUSH 后立即 LTRIM）
Overview "最近操作"：读取最近 20 条
独立日志页面：分页读取全量（最多 1000 条）
超出即淘汰，旧日志不保留（无持久化要求）
```

> **重要：区分两个 Redis 维度**
>
> -   **平台 Redis**：存站点配置、缓存、锁、操作日志，通过
>     `OPS_REDIS_URL` 连接，全局唯一；
> -   **被监控的业务 Redis**：站点里配置的 redis 实例，是"监控对象"，
>     按站点配置动态连接。
>
> 即使两者物理上恰好是同一台 Redis，也必须通过**不同连接、不同 DB**
> 逻辑隔离。代码中严禁混用连接对象：平台 Redis 客户端由 core/redis.py
> 统一管理，业务 Redis 连接由 redis 模块的 provider 按配置创建。

## 17.2 前端展示

-   Overview 页"最近操作"卡片；
-   独立的操作日志页面（全量分页）。

------------------------------------------------------------------------

# 18. API 设计

``` text
# 站点管理
GET    /api/sites
POST   /api/sites
GET    /api/sites/{site_id}
PUT    /api/sites/{site_id}
DELETE /api/sites/{site_id}

POST   /api/sites/export
POST   /api/sites/import

# 连接测试（保存前，直接提交配置）
POST   /api/test-connection
       Body: { "type": "server|redis|mq|robot", "config": {...} }

# Overview
GET    /api/sites/{site_id}/overview

# Server（只读）
GET    /api/sites/{site_id}/servers
GET    /api/sites/{site_id}/servers/{server_id}/metrics
GET    /api/sites/{site_id}/servers/{server_id}/processes
POST   /api/sites/{site_id}/servers/{server_id}/test

# Redis
GET    /api/sites/{site_id}/redis
POST   /api/sites/{site_id}/redis
PUT    /api/sites/{site_id}/redis/{redis_id}
DELETE /api/sites/{site_id}/redis/{redis_id}
POST   /api/sites/{site_id}/redis/{redis_id}/test

GET    /api/sites/{site_id}/redis/{redis_id}/info
GET    /api/sites/{site_id}/redis/{redis_id}/keys
       ?db=0&pattern=robot:*&cursor=0&count=100
GET    /api/sites/{site_id}/redis/{redis_id}/key
       ?db=0&key=robot:001

POST   /api/sites/{site_id}/redis/{redis_id}/operations
       Body: { "op": "set|delete|expire", "db": 0, "key": "...", ... }

# ActiveMQ
GET    /api/sites/{site_id}/mq
GET    /api/sites/{site_id}/mq/{mq_id}/overview
GET    /api/sites/{site_id}/mq/{mq_id}/queues
GET    /api/sites/{site_id}/mq/{mq_id}/addresses
POST   /api/sites/{site_id}/mq/{mq_id}/test

# Robot
GET    /api/sites/{site_id}/robots
GET    /api/sites/{site_id}/robots/{robot_id}
POST   /api/sites/{site_id}/robots/{robot_id}/test

# 操作日志
GET    /api/audit
```

------------------------------------------------------------------------

# 19. 前端技术栈

``` text
Vue 3
TypeScript
Vite
Pinia
Vue Router
Naive UI
Axios
ECharts
```

不使用 MUI，因为 MUI 是 React 生态 UI 框架。

------------------------------------------------------------------------

# 20. 前端模块化与扩展设计（重点）

> **要求：后续新增模块（数据库监控、Docker 监控等）时，只新增目录 + 一行注册，不修改核心框架代码。**

## 20.1 目录结构

``` text
src/
├── api/                    # 通用 axios 封装
├── components/             # 通用组件（状态徽标、倒计时确认框等）
├── layouts/                # 主布局（侧边栏 / 顶栏 / Site 切换器）
├── modules/                # ★ 功能模块，每个模块自包含
│   ├── registry.ts         # 模块注册中心
│   ├── overview/
│   │   ├── index.ts        # defineOpsModule({...})
│   │   ├── api.ts
│   │   └── components/
│   ├── server/
│   ├── redis/
│   ├── mq/
│   └── robot/
├── router/
├── stores/                 # site context 等全局 store
├── types/
├── utils/
└── views/
```

## 20.2 模块定义

``` ts
// modules/server/index.ts
import type { OpsModule } from '../registry'
import ServerView from './ServerView.vue'

const module: OpsModule = {
  id: 'server',
  title: 'Server',
  order: 2,
  icon: 'desktop-outline',
  routePath: 'server',          // /console/site/:siteId/server
  view: ServerView,
}

export default module
```

## 20.3 核心如何消费注册表

``` text
layouts       遍历 registry → 渲染侧边栏菜单（按 order 排序）
router        遍历 registry → 动态生成 /console/site/:siteId/:moduleId
Site Store    切换 site → 所有模块路由参数自动变化，模块自行响应
```

## 20.4 新增一个模块的完整步骤

以"数据库监控"为例：

``` text
1. 新建 src/modules/database/
     index.ts / api.ts / components/
2. 在 index.ts 中 defineOpsModule({...})
3. 完成
```

不需要修改 layout、router、store、菜单等任何核心代码。

## 20.5 通用组件沉淀

为避免各模块重复造轮子，以下做成通用组件：

``` text
StatusBadge          Healthy / Warning / Critical / Unknown
CountdownConfirm     带倒计时的危险操作确认框
MetricCard           指标卡片
TrendSpark           迷你趋势图
ResourceTestButton   连接测试按钮（含 loading / 结果展示）
DataTable            通用表格封装
```

新模块直接复用，保证风格统一。

------------------------------------------------------------------------

# 21. Site Context（前端）

Pinia 保存当前站点：

``` text
currentSiteId
currentSite
```

路由：

``` text
/console/site/{site_id}/overview
/console/site/{site_id}/server
/console/site/{site_id}/redis
/console/site/{site_id}/mq
/console/site/{site_id}/robot
```

切换 Site 后所有模块自动切换（路由参数变化，模块内 watch 响应重新加载）。

顶栏提供 Site 下拉切换器，切换后停留在当前模块。

------------------------------------------------------------------------

# 22. UI 设计原则

目标：

> 专业内部工具，而不是 AI 生成的后台模板。

避免：

-   大面积渐变
-   过多发光
-   过多圆角
-   巨型数字卡片
-   无意义动画
-   大量彩色图标
-   复杂玻璃拟态

推荐：

``` text
深色 / 浅色均可
信息密度适中
明确层级
状态颜色克制
表格为主
图表辅助
```

状态：

``` text
Green   Healthy
Yellow  Warning
Red     Critical
Gray    Unknown
```

------------------------------------------------------------------------

# 23. 后端技术栈

``` text
Python 3.13

FastAPI
Pydantic v2

redis-py
AsyncSSH
httpx

APScheduler
Loguru
```

不引入 ORM / SQLAlchemy / Alembic。

------------------------------------------------------------------------

# 24. 后端目录与模块注册（重点）

> **与前端同标准：新增模块只新增目录 + 注册，不修改核心代码。**

``` text
backend/
└── app/
    ├── main.py                # 创建 app，调用 modules 注册
    ├── core/
    │   ├── config.py          # OPS_REDIS_URL 等环境配置
    │   ├── redis.py           # 平台 Redis 连接（配置 + 缓存 + 锁）
    │   ├── cache.py           # 短 TTL 缓存装饰器 / 工具
    │   ├── registry.py        # 模块注册中心
    │   ├── oplog.py           # 操作日志
    │   └── logging.py
    │
    ├── shared/                # 通用基础设施
    │   ├── timeout.py         # 统一超时策略
    │   ├── concurrency.py     # 并发信号量
    │   └── errors.py          # 统一错误响应
    │
    └── modules/               # ★ 功能模块，每个模块自包含
        ├── __init__.py        # register_all(): 收集并注册所有模块
        │
        ├── overview/
        │   ├── __init__.py    # register_module(app)
        │   ├── api.py         # APIRouter
        │   └── service.py
        │
        ├── sites/             # 站点 + 资源配置管理 + 导入导出
        │   ├── api.py
        │   └── service.py
        │
        ├── server/
        │   ├── api.py
        │   ├── service.py
        │   └── provider.py    # ServerMetricsProvider / SSH 实现 + 命令白名单
        │
        ├── redis/
        │   ├── api.py
        │   ├── service.py
        │   └── provider.py    # 目标 Redis 连接管理
        │
        ├── mq/
        │   ├── api.py
        │   ├── service.py
        │   └── provider.py    # ArtemisProvider（Jolokia）
        │
        ├── robot/
        │   ├── api.py
        │   ├── service.py
        │   └── provider.py    # RobotProvider（HTTP）
        │
        └── audit/
            └── api.py
```

## 24.1 注册机制

``` python
# app/modules/server/__init__.py
from fastapi import FastAPI
from .api import router

def register_module(app: FastAPI):
    app.include_router(router, prefix="/api")
```

``` python
# app/modules/__init__.py
from . import overview, sites, server, redis, mq, robot, audit

def register_all(app: FastAPI):
    for m in (overview, sites, server, redis, mq, robot, audit):
        m.register_module(app)
```

## 24.2 新增一个模块的完整步骤

以"数据库监控"为例：

``` text
1. 新建 app/modules/database/
     api.py / service.py / provider.py / __init__.py
2. 在 modules/__init__.py 的注册列表中加一行
3. 完成
```

main.py、core、shared 均不需要改动。

## 24.3 Provider 约定

每个模块的 provider 层遵守统一接口风格：

``` text
Server
ServerMetricsProvider
└── SSHServerMetricsProvider
    └──（未来）PrometheusServerMetricsProvider

MQ
MessageBrokerProvider
└── ArtemisProvider
    └──（未来）RabbitMQProvider

Robot
RobotProvider
└── HttpRobotProvider
```

未来引入新实现，业务层与 API 层不动。

------------------------------------------------------------------------

# 25. 部署

## 25.1 Docker Compose

Compose 包含两个服务：

``` text
services:
  backend
  ops-nginx      # 平台自有 nginx 容器（新建，不影响现有 nginx）
```

外部依赖（不纳入平台 Compose，不二次构建）：

``` text
现有 Redis       # 平台配置 + 缓存 + 锁（独立 DB，OPS_REDIS_URL 接入）
```

## 25.2 前端交付与 nginx 端口说明

前端构建产物（dist/）由**平台自有的 ops-nginx 容器**托管：

``` text
ops-nginx
  ├── /            → frontend dist/
  └── /api         → proxy_pass backend:8000
```

**关于与现有 nginx 的端口冲突问题：**

-   一台宿主机上可以同时运行多个 nginx 容器，前提是它们映射的**宿主机
    端口不同**；
-   现有 nginx 已占用 80 端口，平台 nginx 映射到其他端口，例如：

``` text
ops-nginx:
  ports:
    - "8090:80"       # 宿主机 8090 → 容器 80
```

-   访问方式：`http://<host>:8090`；
-   端口号通过 Compose `.env` 配置，可按现场空闲端口调整；
-   **完全不需要改动现有 nginx 的任何配置**，两个 nginx 互不干扰。

备选方案：backend 直接托管前端静态文件（单容器，无 nginx），适合极简
部署场景。默认推荐 ops-nginx 方案。

## 25.3 环境变量

``` text
OPS_REDIS_URL=redis://existing-redis:6379/5    # 平台 Redis
OPS_LOG_LEVEL=INFO
SSH_CONNECT_TIMEOUT=5
SSH_COMMAND_TIMEOUT=10
HTTP_CONNECT_TIMEOUT=5
HTTP_READ_TIMEOUT=10
REDIS_CONNECT_TIMEOUT=5
MQ_API_TIMEOUT=10
```

## 25.4 Volume

``` text
backend-logs       # 应用日志
```

无配置持久化 Volume 要求（配置在现有 Redis 中）。

------------------------------------------------------------------------

# 26. 超时与重试

所有外部系统连接必须有 timeout：

``` text
SSH connect timeout     3~5s
SSH command timeout     5~10s
HTTP connect timeout    3~5s
HTTP read timeout       5~10s
Redis connect timeout   3~5s
MQ API timeout          5~10s
```

重试策略：

``` text
Connection Error
    ↓
最多 1~2 次 retry
    ↓
仍然失败
    ↓
返回 UNKNOWN / ERROR
```

避免多个用户同时触发故障系统导致重试风暴。

------------------------------------------------------------------------

# 27. 并发控制

外部系统查询限制并发：

``` text
SSH max concurrent = N
MQ max concurrent = N
Robot API max concurrent = N
```

避免：

``` text
100 用户 × 100 Server × SSH
```

造成平台自身资源耗尽。

------------------------------------------------------------------------

# 28. Error Handling

外部系统异常不能导致 FastAPI 请求直接崩溃。

统一：

``` json
{
  "success": false,
  "error_code": "REMOTE_CONNECTION_FAILED",
  "message": "Unable to connect to server",
  "resource": "server-01"
}
```

前端显示：

``` text
● Healthy
⚠ Warning
✕ Critical
? Unknown
```

------------------------------------------------------------------------

# 29. 日志

应用日志（Loguru）：

``` text
logs/
├── app/
├── audit/
└── error/
```

日志需要：

``` text
Rotation
Retention
Structured Context
```

关键日志包含：

``` text
request_id
site_id
resource_id
operation
```

（无 user_id，系统无用户概念。）

------------------------------------------------------------------------

# 30. V1 功能范围

## 必须实现

### Platform

-   [ ] Site Management（增删改查 + 启用禁用）
-   [ ] 配置导出 / 导入（JSON）
-   [ ] 连接测试（Server / Redis / MQ / Robot，含保存前测试）
-   [ ] Threshold（阈值，全局默认 + 站点 / 资源覆盖）
-   [ ] 操作日志（无用户维度）

### Overview

-   [ ] Site Health
-   [ ] Server Health
-   [ ] Redis Health
-   [ ] MQ Health
-   [ ] Robot Health
-   [ ] Issue Summary
-   [ ] 最近操作

### Server（只读）

-   [ ] CPU / Memory / Disk / Load / Network
-   [ ] Top Process
-   [ ] Diagnosis（阈值 + 状态色）

### Redis

-   [ ] DB Browser（SCAN）
-   [ ] Search（Pattern / Type / 分页 / Load More）
-   [ ] Key Detail（String / Hash / List / Set / ZSet / TTL / Memory）
-   [ ] 编辑保存（RedisDesktop 风格：文本 / JSON 直接编辑）
-   [ ] 删除（5 秒倒计时二次确认）
-   [ ] 危险命令禁止

### ActiveMQ

-   [ ] Connection / Broker / JVM
-   [ ] Queue / Address / Consumer / Producer
-   [ ] Backlog（含短时趋势）
-   [ ] Diagnosis

### Robot

-   [ ] Robot List / Status / Detail

### 框架

-   [ ] 前端模块注册机制
-   [ ] 后端模块注册机制
-   [ ] 通用组件（StatusBadge / CountdownConfirm / ResourceTestButton 等）

## V1 明确不实现

``` text
用户 / 登录 / RBAC
Secret 加密管理
Prometheus / Grafana
Kafka / Celery
WebSocket
Kubernetes
Elasticsearch
复杂告警中心
自动修复
任意 Shell 执行
SSH 终端 / 文件操作
完整历史时序数据库
复杂报表
FLUSHDB / FLUSHALL / CONFIG / EVAL 等危险命令
```

## V2 候选

``` text
数据库监控（PostgreSQL / MySQL）—— 通过模块注册机制接入
Docker 监控
Prometheus / Node Exporter
历史趋势
通知（Email / Webhook / 企业微信 / 钉钉 / 飞书）
更多 MQ
PLC
自动诊断
```

------------------------------------------------------------------------

# 31. 开发顺序

建议严格按照：

``` text
Phase 1
前后端基础工程 + 模块注册框架
↓
Phase 2
Site 管理（含配置导入导出）
↓
Phase 3
Server Adapter + 连接测试
↓
Phase 4
Server Diagnosis
↓
Phase 5
Redis Adapter + 连接测试
↓
Phase 6
Redis Browser + Operations（编辑 / 删除 / 倒计时确认）
↓
Phase 7
Artemis Adapter + 连接测试
↓
Phase 8
Robot Adapter + 连接测试
↓
Phase 9
Overview
↓
Phase 10
操作日志 + 稳定性（超时 / 重试 / 并发控制）
↓
Phase 11
Docker Compose（单 backend 服务）
↓
Phase 12
测试与稳定性优化
```

不要一开始同时开发所有模块。

------------------------------------------------------------------------

# 32. 测试要求

## Unit Test

``` text
Diagnosis / Threshold
Cache
Adapter
Parser
命令白名单（不可被绕过）
Redis 操作参数校验
```

## Integration Test

``` text
SSH
Redis
Artemis
Robot API
连接测试
```

## API Test

``` text
Site
Server
Redis
MQ
Robot
连接测试
配置导出导入
```

## Frontend Test

``` text
Site Switch
Module Switch
Redis Operation
Danger Confirmation（倒计时）
Connection Test
Error State
Loading State
```

## E2E

至少覆盖：

``` text
选择 Site
查看 Overview
查看 Server
查看 Redis
编辑 Redis Key
删除 Redis Key（倒计时确认）
测试连接
查看 MQ
查看 Robot
```

------------------------------------------------------------------------

# 33. 验收标准

系统达到以下条件才认为 V1 完成：

1.  Docker Compose 一条命令可以启动 backend + 平台 nginx（独立端口，不与现有 nginx 冲突，不构建 Redis）；
2.  平台正确接入现有 Redis（配置 + 缓存）；
3.  Site 配置支持导出 / 导入 JSON；
4.  可以添加多个 Server / Redis / Artemis / Robot；
5.  每种资源配置都有连接测试按钮，且支持保存前测试；
6.  用户切换 Site 后所有模块自动切换；
7.  Server 查询失败不会导致平台异常，显示 Unknown；
8.  Server 页面纯只读，不存在任何操作入口；
9.  Redis 查询使用 SCAN，不使用 KEYS \*；
10. Redis value 可直接编辑（文本 / JSON）并保存；
11. Redis 删除操作有 5 秒倒计时二次确认；
12. FLUSHDB / FLUSHALL / CONFIG / EVAL 等危险命令无任何入口；
13. 所有修改 / 删除操作都记录操作日志（无用户字段）；
14. 外部连接都有 timeout，不存在无限 retry；
15. 多用户同时查询不会产生大量重复 SSH（缓存 + 锁合并）；
16. 平台自身资源占用保持较低；
17. 新增一个前端模块只需新增目录 + 注册，不改核心代码（以一个 demo 模块验证）；
18. 新增一个后端模块只需新增目录 + 注册，不改核心代码（以一个 demo 模块验证）。

------------------------------------------------------------------------

# 34. 核心设计结论

第一版最终架构：

``` text
Vue 3（模块注册式）
  +
FastAPI（模块注册式）
  +
现有 Redis（配置 + 缓存 + 锁）
  +
Docker Compose（backend + 平台 nginx，独立端口）
```

外部系统：

``` text
Linux（SSH 只读诊断）
Redis（唯一可写资源）
ActiveMQ Artemis
Robot API
```

均通过 Adapter 访问。

核心体验：

> **少输入、少等待、少切系统、快速定位问题。**

------------------------------------------------------------------------

# 35. 设计决策记录

## Decision 001

### 配置存储使用现有 Redis，不做持久化

原因：配置量小、关系简单；平台复用现有 Redis 容器，不为"企业级"强行增加数据库与持久化设施。

兜底：配置导出 / 导入 JSON。

## Decision 002

### 不采用 Prometheus

原因：当前目标是故障诊断，而不是长期指标监控。未来有历史趋势需求时再增加。

## Decision 003

### 不采用 WebSocket

原因：实时性要求不足以证明 WebSocket 的必要性。

采用：按需 HTTP + 短 TTL Cache + 手动 / 低频刷新。

## Decision 004

### 不采用长连接 SSH

原因：服务器数量可能较多，长连接会增加连接管理复杂度和资源占用。

采用：按需 SSH + 单次聚合查询 + 短 TTL Cache。

## Decision 005（v0.2 修订）

### 无用户体系

原因：内部使用，用户体系带来的登录、权限、会话维护成本远大于收益。

结果：无登录、无 RBAC；操作日志只记录操作本身。

## Decision 006（v0.2 新增）

### Server 只读，Redis 唯一可写

原因：正常情况下不应给用户提供 SSH 操作途径；服务器信息以看为主。Redis 的查询修改删除是真实运维需求，保留并提供 RedisDesktop 风格的编辑体验与倒计时确认保护。

## Decision 007（v0.2 修订）

### Redis 复用现有容器；nginx 新建平台自有容器

原因：

-   Redis 已有现成容器，直接通过 `OPS_REDIS_URL` 接入即可；
-   前端静态资源托管若复用现有 nginx，需要改动其配置，可能影响现有服务；
-   新建一个独立的 ops-nginx 容器，映射到不同宿主机端口（默认 8090，
     可配置），与现有 nginx（80 端口）互不冲突。

结果：Compose 包含 backend + ops-nginx 两个服务；Redis 通过
`OPS_REDIS_URL` 接入现有容器。

## Decision 008（v0.2 新增）

### 前后端统一模块注册机制

原因：Server 等模块后续可能扩展为数据库监控等多种资源类型，必须保证新增模块改动局限在模块目录内。

结果：前端 modules/registry + 后端 modules/register_all，新增模块 = 新增目录 + 一行注册。

------------------------------------------------------------------------

# 36. 最终目标

这个平台最终不是：

> "又一个 Grafana。"

而应该是：

> **一个内部工程人员遇到服务器 / Redis / MQ / Robot
> 问题时，第一时间打开的统一诊断入口。**

理想操作路径：

``` text
打开平台（无需登录）
    ↓
选择站点
    ↓
看到 Overview
    ↓
发现：
MQ WARNING
Server WARNING
    ↓
点击 MQ
    ↓
发现 Queue backlog
    ↓
点击 Queue
    ↓
发现 Consumer 数量异常
    ↓
进一步定位对应服务
```

或者：

``` text
Server WARNING
    ↓
CPU 92%
    ↓
Top Process
    ↓
java PID 1234
    ↓
定位问题服务
```

Redis 运维路径：

``` text
Redis Tab
    ↓
SCAN / 搜索 Key
    ↓
查看 Value（文本 / JSON）
    ↓
直接编辑保存（确认）
    ↓
或删除（5 秒倒计时确认）
```

最终核心体验：

> **少输入、少等待、少切系统、快速定位问题。**
