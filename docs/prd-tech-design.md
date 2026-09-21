# 内部服务器运维诊断平台

## PRD + 技术设计文档

> 文档版本：v0.1\
> 文档状态：需求与技术方案初稿\
> 目标：作为后续 AI 辅助设计、开发、测试的基准文档\
> 部署方式：Docker Compose\
> 使用范围：公司内部运维 / 开发 / 测试人员

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
-   当 CPU、内存、磁盘、MQ、Redis
    等出现异常时，需要登录不同服务器逐一排查；
-   运维人员需要重复输入服务器、Redis、MQ 等连接信息；
-   不同系统的信息分散，无法从站点维度快速查看；
-   希望通过一个统一 Web 平台快速判断"哪里异常、为什么异常"。

系统的核心目标不是持续采集海量指标，而是：

> **选择站点 → 快速查看整体健康状态 → 定位异常资源 → 查看详细诊断信息 →
> 必要时执行受保护的运维操作。**

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

所有模块自动继承当前站点配置，尽量避免用户重复输入
IP、账号、密码等信息。

------------------------------------------------------------------------

## 2.2 Diagnose \> Monitor

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

------------------------------------------------------------------------

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

对于首页健康摘要，可以进行低频后台检查。

------------------------------------------------------------------------

## 2.4 Short Cache

对高成本查询使用短 TTL 缓存：

``` text
Server Metrics      5~10 秒
MQ Overview         5~10 秒
Redis Info          5~10 秒
Robot Status        5~10 秒
```

避免多个用户同时打开同一页面时重复连接外部系统。

------------------------------------------------------------------------

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

------------------------------------------------------------------------

## 2.6 Simple but Extensible

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

# 3. 用户与使用场景

## 3.1 主要用户

### 运维人员

关注：

-   服务器健康状态
-   MQ 状态
-   Redis 状态
-   Robot 状态
-   异常诊断
-   必要的运维操作

### 开发人员

关注：

-   服务所在服务器
-   Redis Key
-   MQ Queue / Topic
-   Robot 状态
-   进程状态

### 管理人员

关注：

-   当前站点整体健康情况
-   是否存在异常资源
-   异常数量

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

未来可以扩展：

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

一个 Site 可以包含多个资源。

------------------------------------------------------------------------

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
servers
redis_instances
mq_instances
robots
```

------------------------------------------------------------------------

# 6. 配置持久化方案

## 6.1 是否引入 PostgreSQL

第一版**不引入 PostgreSQL**。

原因：

-   当前配置量很小；
-   主要数据是 Site 和外部系统连接配置；
-   不需要复杂关系查询；
-   不需要大规模历史数据；
-   Docker Compose 中减少一个服务；
-   降低部署、备份、升级和运维成本。

------------------------------------------------------------------------

## 6.2 推荐方案：平台自有 Redis 作为配置存储

系统已经需要 Redis 作为缓存，因此第一版可以让平台使用一个独立 Redis
实例，同时承担：

``` text
配置存储
短期缓存
分布式锁
短期状态
```

注意：

> **平台自己的 Redis 与被监控的业务 Redis 必须逻辑隔离，推荐直接使用独立
> Redis Container。**

例如：

``` text
ops-redis
    ↓
平台配置 + Cache

site-redis-01
    ↓
被监控的业务 Redis
```

------------------------------------------------------------------------

## 6.3 Redis 配置结构

不建议把所有数据散落成大量 Key。

推荐使用 Hash：

``` text
ops:site:{site_id}
```

例如：

``` text
ops:site:shenzhen-test
```

Hash：

``` text
name
description
enabled
created_at
updated_at
```

资源配置可以独立：

``` text
ops:site:{site_id}:servers
ops:site:{site_id}:redis
ops:site:{site_id}:mq
ops:site:{site_id}:robots
```

例如：

``` text
ops:site:shenzhen-test:redis
```

Hash：

``` text
redis-01 = JSON
redis-02 = JSON
```

其中 JSON 包含：

``` json
{
  "name": "redis-01",
  "host": "10.10.1.20",
  "port": 6379,
  "username": "",
  "password": "",
  "db": 0,
  "enabled": true
}
```

------------------------------------------------------------------------

## 6.4 为什么暂时不使用 PostgreSQL

第一版的数据特点：

``` text
配置数据少
关系简单
写入频率低
查询简单
```

因此：

``` text
Redis Hash
```

已经可以满足。

但是需要明确：

> 如果未来加入大量审计记录、用户体系、复杂权限、历史指标、报表、复杂关联查询，则应该重新评估
> SQLite / PostgreSQL。

当前不为了"企业级"三个字强行增加数据库。

------------------------------------------------------------------------

# 7. Redis 作为配置存储的边界

Redis 作为配置源是可行的，但必须明确它不是永远最优的方案。

如果未来出现：

``` text
用户 > 1000
审计记录 > 数百万
复杂 RBAC
大量历史数据
报表
多实例高可用
复杂查询
```

则考虑迁移：

``` text
PostgreSQL
```

当前版本保持简单。

------------------------------------------------------------------------

# 8. 用户与权限

第一版支持基础 RBAC。

角色建议：

``` text
VIEWER
OPERATOR
ADMIN
```

权限示例：

  操作               VIEWER   OPERATOR   ADMIN
  ---------------- -------- ---------- -------
  查看 Overview           ✓          ✓       ✓
  查看 Server             ✓          ✓       ✓
  查看 Redis              ✓          ✓       ✓
  查看 MQ                 ✓          ✓       ✓
  查看 Robot              ✓          ✓       ✓
  修改 Redis Key          ✕          ✓       ✓
  删除 Redis Key          ✕          ✓       ✓
  修改 Site 配置          ✕          ✕       ✓
  执行危险操作            ✕     按权限       ✓

第一版认证可以采用平台自身简单账号体系。

未来如公司已有统一身份认证，可增加 OIDC / OAuth2 / Keycloak。

------------------------------------------------------------------------

# 9. Overview 首页

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

------------------------------------------------------------------------

## 9.1 异常摘要

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

------------------------------------------------------------------------

## 9.2 最近操作

显示最近的关键操作：

``` text
13:42 Redis DELETE
13:38 Site configuration changed
13:21 MQ query
```

------------------------------------------------------------------------

# 10. Server 模块

## 10.1 查询方式

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

------------------------------------------------------------------------

## 10.2 Server Metrics

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

------------------------------------------------------------------------

# 11. Server 查询原则

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
执行聚合查询
      ↓
CPU
Memory
Disk
Load
Network
      ↓
关闭
```

或者在条件允许时使用一次远程命令返回结构化结果。

------------------------------------------------------------------------

# 12. Server Provider 抽象

定义：

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

------------------------------------------------------------------------

# 13. Server 诊断规则

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

------------------------------------------------------------------------

## 13.1 诊断输出

例如：

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

------------------------------------------------------------------------

# 14. ActiveMQ Artemis 模块

目标版本：

``` text
Artemis 2.19
```

推荐优先通过 Artemis Management API / Jolokia 获取管理数据。

------------------------------------------------------------------------

## 14.1 Broker Overview

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

------------------------------------------------------------------------

## 14.2 JVM

显示：

``` text
Heap Used
Heap Max
Non Heap
Threads
GC
```

------------------------------------------------------------------------

## 14.3 Queue

显示：

``` text
Queue Name
Message Count
Consumer Count
Delivering Count
Messages Added
Messages Acknowledged
```

------------------------------------------------------------------------

## 14.4 Address / Topic

显示：

``` text
Address
Message Count
Consumer Count
Producer Count
```

------------------------------------------------------------------------

## 14.5 MQ 诊断

重点检测：

``` text
Queue backlog
Consumers = 0
Messages 持续增长
Delivering 数量异常
Broker CPU
JVM Memory
```

------------------------------------------------------------------------

# 15. Queue 堆积趋势

不要只显示：

``` text
Messages = 12381
```

还可以比较短时间前的值：

``` text
Current:
12381

5 minutes ago:
2341

Growth:
+10040
```

如果持续增长：

``` text
WARNING
Backlog increasing rapidly
```

第一版不需要建立完整时序数据库，可以使用 Redis 保存短期采样数据。

------------------------------------------------------------------------

# 16. Redis 模块

Redis 模块既可以查询被监控 Redis，也可以执行受控操作。

------------------------------------------------------------------------

## 16.1 Redis Overview

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

------------------------------------------------------------------------

# 17. Redis DB Browser

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

禁止生产环境使用：

``` text
KEYS *
```

------------------------------------------------------------------------

## 17.1 Key Search

支持：

``` text
Pattern
Type
Pagination
```

例如：

``` text
robot:*
```

使用：

``` text
SCAN cursor MATCH robot:* COUNT 100
```

前端支持：

``` text
Load More
```

避免一次性加载大量 Key。

------------------------------------------------------------------------

# 18. Redis Key Detail

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

------------------------------------------------------------------------

# 19. Redis 操作保护

危险操作：

``` text
SET
DELETE
EXPIRE
修改 Hash
修改 List
修改 Set
修改 ZSet
```

需要确认。

危险程度更高的命令：

``` text
FLUSHDB
FLUSHALL
CONFIG
SHUTDOWN
SCRIPT FLUSH
EVAL
```

第一版默认禁止。

------------------------------------------------------------------------

# 20. Redis 二次确认

前端：

``` text
You are about to delete:

robot:001

This operation cannot be undone.

Please wait 5 seconds...

[ Delete ]
```

按钮 5 秒内不可点击。

注意：

> 倒计时只是 UI 防误操作机制，不能作为后端安全机制。

后端仍然必须：

``` text
Authentication
Authorization
Operation Validation
Audit
```

------------------------------------------------------------------------

# 21. Robot 模块

Robot 通过 HTTP API 查询。

第一版定义统一接口：

``` text
get_robot_list()
get_robot_status()
get_robot_detail()
```

业务层不直接依赖具体 Robot API。

------------------------------------------------------------------------

# 22. Robot 页面

列表：

``` text
Robot ID
Name
Status
Battery
Current Station
Task
Last Update
```

详情：

``` text
Basic Information
Status
Battery
Position
Task
Error
```

------------------------------------------------------------------------

# 23. Cache 设计

平台自身 Redis 负责缓存。

示例：

``` text
ops:cache:server:{server_id}:metrics
TTL 5s

ops:cache:mq:{mq_id}:overview
TTL 5s

ops:cache:redis:{redis_id}:info
TTL 5s

ops:cache:robot:{robot_id}:status
TTL 5s
```

------------------------------------------------------------------------

# 24. 请求合并

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
Lock
   ↓
SSH Query
   ↓
Cache
   ↓
Return
```

第一版可以使用 Redis Lock 或简单短 TTL 锁。

------------------------------------------------------------------------

# 25. 后台健康检查

后台只做轻量检查。

推荐：

``` text
30 秒
```

检查：

``` text
Server CPU
Server Memory
Disk
MQ Connection
MQ Backlog
Redis Connection
Redis Memory
```

详细信息：

``` text
按需查询
```

------------------------------------------------------------------------

# 26. 不采用长连接

第一版不使用：

``` text
长连接 SSH
WebSocket
持续 MQ Connection
持续 Redis Connection
```

除非后续真实需求证明必要。

------------------------------------------------------------------------

# 27. Scheduler

可以使用：

``` text
APScheduler
```

职责：

``` text
健康检查
短期指标采样
缓存刷新
```

不要让 Scheduler 负责所有业务逻辑。

------------------------------------------------------------------------

# 28. Audit Log

所有有副作用的操作必须记录。

记录：

``` text
User
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
User: admin
Site: shenzhen-test
Resource: redis-01
Operation: DELETE_KEY
Target: robot:001
Result: SUCCESS
```

第一版可以存 Redis。

如果未来审计数据量明显增长，再迁移 PostgreSQL。

------------------------------------------------------------------------

# 29. Secret 管理

以下内容属于敏感配置：

``` text
SSH Password
SSH Private Key
Redis Password
MQ Username
MQ Password
Robot API Token
```

禁止明文返回前端。

推荐：

``` text
Redis
  ↓
Encrypted Secret
  ↓
Application Master Key
```

Master Key：

``` text
Docker Secret
```

或者环境变量注入。

------------------------------------------------------------------------

# 30. API 设计

建议：

``` text
/api/auth

/api/sites
/api/sites/{site_id}

/api/sites/{site_id}/overview

/api/sites/{site_id}/servers
/api/sites/{site_id}/servers/{server_id}/metrics
/api/sites/{site_id}/servers/{server_id}/processes

/api/sites/{site_id}/redis
/api/sites/{site_id}/redis/{redis_id}/info
/api/sites/{site_id}/redis/{redis_id}/keys
/api/sites/{site_id}/redis/{redis_id}/key
/api/sites/{site_id}/redis/{redis_id}/operations

/api/sites/{site_id}/mq
/api/sites/{site_id}/mq/{mq_id}/overview
/api/sites/{site_id}/mq/{mq_id}/queues
/api/sites/{site_id}/mq/{mq_id}/addresses

/api/sites/{site_id}/robots
/api/sites/{site_id}/robots/{robot_id}

/api/audit
```

------------------------------------------------------------------------

# 31. 前端技术栈

推荐：

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

# 32. 前端结构

``` text
src/
├── api/
├── components/
├── layouts/
├── modules/
│   ├── overview/
│   ├── server/
│   ├── redis/
│   ├── mq/
│   └── robot/
├── router/
├── stores/
├── types/
├── utils/
└── views/
```

------------------------------------------------------------------------

# 33. Site Context

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

切换 Site 后所有模块自动切换。

------------------------------------------------------------------------

# 34. UI 设计原则

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

# 35. 路由与模块切换

推荐：

``` text
Site
 ├── Overview
 ├── Server
 ├── Redis
 ├── ActiveMQ
 └── Robot
```

未来：

``` text
 ├── Docker
 ├── PLC
 ├── Database
 └── Service
```

模块采用注册式设计，避免大量 if/else。

------------------------------------------------------------------------

# 36. 后端技术栈

``` text
Python 3.13

FastAPI
Pydantic v2
SQLAlchemy：第一版不启用
Alembic：第一版不启用

redis-py
AsyncSSH
httpx

APScheduler
Loguru
```

第一版不强制引入 ORM。

------------------------------------------------------------------------

# 37. 后端目录建议

``` text
backend/
└── app/
    ├── main.py
    ├── api/
    │   ├── auth.py
    │   ├── sites.py
    │   ├── servers.py
    │   ├── redis.py
    │   ├── mq.py
    │   └── robots.py
    │
    ├── domain/
    │   ├── site/
    │   ├── server/
    │   ├── redis/
    │   ├── mq/
    │   └── robot/
    │
    ├── services/
    │   ├── monitoring/
    │   ├── diagnostics/
    │   ├── cache/
    │   └── audit/
    │
    ├── infrastructure/
    │   ├── ssh/
    │   ├── redis/
    │   ├── artemis/
    │   └── http/
    │
    ├── scheduler/
    └── core/
        ├── config.py
        ├── security.py
        └── logging.py
```

------------------------------------------------------------------------

# 38. Adapter 设计

## Server

``` text
ServerMetricsProvider
└── SSHServerMetricsProvider
```

未来：

``` text
└── PrometheusServerMetricsProvider
```

## MQ

``` text
MessageBrokerProvider
└── ArtemisProvider
```

未来：

``` text
└── RabbitMQProvider
```

## Robot

``` text
RobotProvider
└── HttpRobotProvider
```

------------------------------------------------------------------------

# 39. Docker Compose

第一版：

``` text
nginx
frontend
backend
ops-redis
```

结构：

``` text
                    Nginx
                      │
              ┌───────┴───────┐
              │               │
          Frontend         Backend
                              │
                              ↓
                          ops-redis
                              │
                    ┌─────────┼─────────┐
                    ↓         ↓         ↓
                  Config    Cache      Lock
```

外部系统：

``` text
Linux Server
Redis
ActiveMQ Artemis
Robot API
```

不纳入平台 Compose。

------------------------------------------------------------------------

# 40. Docker Volume

至少：

``` text
ops-redis-data
backend-logs
```

配置数据通过：

``` text
ops-redis-data
```

持久化。

------------------------------------------------------------------------

# 41. 日志

应用日志：

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

关键日志必须包含：

``` text
request_id
user_id
site_id
resource_id
operation
```

------------------------------------------------------------------------

# 42. 超时与重试

所有外部系统连接必须有 timeout。

例如：

``` text
SSH connect timeout
SSH command timeout
HTTP connect timeout
HTTP read timeout
Redis connect timeout
MQ API timeout
```

默认：

``` text
Connect Timeout: 3~5s
Read Timeout: 5~10s
```

具体数值后续根据真实环境调整。

------------------------------------------------------------------------

# 43. 重试策略

不能对所有错误无限重试。

推荐：

``` text
Connection Error
    ↓
最多 1~2 次 retry
    ↓
仍然失败
    ↓
返回 UNKNOWN / ERROR
```

避免多个用户同时触发故障系统，导致重试风暴。

------------------------------------------------------------------------

# 44. 并发控制

外部系统查询需要限制并发。

例如：

``` text
SSH max concurrent = N
MQ max concurrent = N
Robot API max concurrent = N
```

避免：

``` text
100 用户
×
100 Server
×
SSH
```

造成平台自身资源耗尽。

------------------------------------------------------------------------

# 45. Error Handling

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

# 46. 安全要求

必须：

``` text
Authentication
Authorization
Secret Encryption
Audit Log
Command Allowlist
Timeout
Rate Limit
```

SSH 命令禁止让用户直接输入任意 shell 命令。

第一版：

> **只允许平台内置的诊断命令。**

例如：

``` text
CPU
Memory
Disk
Load
Process
Network
```

不提供：

``` text
Execute arbitrary shell command
```

------------------------------------------------------------------------

# 47. Redis 安全

平台连接目标 Redis 时：

``` text
TLS
Username
Password
DB
```

根据目标 Redis 实际配置选择。

密码允许为空。

例如：

``` json
{
  "host": "10.10.1.20",
  "port": 6379,
  "username": "",
  "password": "",
  "db": 0
}
```

------------------------------------------------------------------------

# 48. MQ 安全

支持：

``` text
HTTP
HTTPS
Username
Password
Jolokia URL
```

密码不返回前端。

------------------------------------------------------------------------

# 49. 未来扩展：Prometheus

第一版不引入。

未来如果需要：

``` text
24h CPU
7d Memory
30d Disk
```

再引入：

``` text
Prometheus
+
Node Exporter
```

架构保持：

``` text
ServerMetricsProvider
├── SSH
└── Prometheus
```

------------------------------------------------------------------------

# 50. 未来扩展：历史指标

如果未来要求：

``` text
趋势
报表
历史查询
容量预测
```

再引入：

``` text
Prometheus
VictoriaMetrics
TimescaleDB
```

不在 V1 中提前增加。

------------------------------------------------------------------------

# 51. V1 功能范围

## 必须实现

### Platform

-   [ ] Login
-   [ ] RBAC
-   [ ] Site Management
-   [ ] Audit Log
-   [ ] Threshold

### Overview

-   [ ] Site Health
-   [ ] Server Health
-   [ ] Redis Health
-   [ ] MQ Health
-   [ ] Robot Health
-   [ ] Issue Summary

### Server

-   [ ] CPU
-   [ ] Memory
-   [ ] Disk
-   [ ] Load
-   [ ] Network
-   [ ] Top Process
-   [ ] Diagnosis

### Redis

-   [ ] DB
-   [ ] SCAN
-   [ ] Search
-   [ ] Key Detail
-   [ ] String
-   [ ] Hash
-   [ ] List
-   [ ] Set
-   [ ] ZSet
-   [ ] TTL
-   [ ] Modify
-   [ ] Delete
-   [ ] Operation Protection

### ActiveMQ

-   [ ] Connection
-   [ ] Broker
-   [ ] JVM
-   [ ] Queue
-   [ ] Address
-   [ ] Consumer
-   [ ] Producer
-   [ ] Backlog
-   [ ] Diagnosis

### Robot

-   [ ] Robot List
-   [ ] Status
-   [ ] Detail

------------------------------------------------------------------------

# 52. V1 明确不实现

``` text
Prometheus
Grafana
Kafka
Celery
WebSocket
Kubernetes
Elasticsearch
复杂告警中心
自动修复
任意 Shell 执行
完整历史时序数据库
复杂报表
```

------------------------------------------------------------------------

# 53. V2 候选

``` text
Docker
Prometheus
Node Exporter
历史趋势
通知
Email
Webhook
企业微信
钉钉
飞书
更多 MQ
更多数据库
PLC
自动诊断
```

------------------------------------------------------------------------

# 54. 核心请求流程

## 查看 Server

``` text
Frontend
   ↓
GET /servers/{id}/metrics
   ↓
FastAPI
   ↓
Cache
   ↓
Cache Hit
   └── Return

Cache Miss
   ↓
Lock
   ↓
SSH Provider
   ↓
Linux Server
   ↓
Parse
   ↓
Diagnosis
   ↓
Redis Cache
   ↓
Return
```

------------------------------------------------------------------------

# 55. 核心设计结论

第一版最终架构：

``` text
Vue 3
  +
FastAPI
  +
Redis
  +
Docker Compose
```

其中 Redis 同时承担：

``` text
平台配置
短期缓存
Lock
短期采样状态
```

外部系统：

``` text
Linux
Redis
ActiveMQ Artemis
Robot API
```

均通过 Adapter 访问。

------------------------------------------------------------------------

# 56. 设计决策记录

## Decision 001

### 不引入 PostgreSQL

原因：

当前数据规模小、关系简单、查询简单。

采用：

``` text
Redis Hash
```

作为第一版配置存储。

未来复杂化后再迁移 PostgreSQL。

------------------------------------------------------------------------

## Decision 002

### 不采用 Prometheus

原因：

当前目标是故障诊断，而不是长期指标监控。

未来有历史趋势需求时再增加。

------------------------------------------------------------------------

## Decision 003

### 不采用 WebSocket

原因：

实时性要求不足以证明 WebSocket 的必要性。

采用：

``` text
按需 HTTP
+
短 TTL Cache
+
手动/低频刷新
```

------------------------------------------------------------------------

## Decision 004

### 不采用长连接 SSH

原因：

服务器数量可能较多，长连接会增加连接管理复杂度和资源占用。

采用：

``` text
按需 SSH
+
单次聚合查询
+
短 TTL Cache
```

------------------------------------------------------------------------

## Decision 005

### 平台 Redis 与业务 Redis 分离

平台 Redis：

``` text
ops-redis
```

目标 Redis：

``` text
site-redis-xxx
```

避免平台自身数据与被监控业务数据混淆。

------------------------------------------------------------------------

# 57. 开发顺序

建议严格按照：

``` text
Phase 1
基础工程
↓
Phase 2
Site 管理
↓
Phase 3
Server Adapter
↓
Phase 4
Server Diagnosis
↓
Phase 5
Redis Adapter
↓
Phase 6
Redis Browser + Operations
↓
Phase 7
Artemis Adapter
↓
Phase 8
Robot Adapter
↓
Phase 9
Overview
↓
Phase 10
RBAC + Audit + Security
↓
Phase 11
Docker Compose
↓
Phase 12
测试与稳定性优化
```

不要一开始同时开发所有模块。

------------------------------------------------------------------------

# 58. 测试要求

至少覆盖：

## Unit Test

``` text
Diagnosis
Threshold
Cache
Adapter
Parser
Permission
```

## Integration Test

``` text
SSH
Redis
Artemis
Robot API
```

## API Test

``` text
Authentication
Authorization
Site
Server
Redis
MQ
Robot
```

## Frontend Test

``` text
Site Switch
Tab Switch
Redis Operation
Danger Confirmation
Error State
Loading State
```

## E2E

至少覆盖：

``` text
Login
选择 Site
查看 Overview
查看 Server
查看 Redis
修改 Redis Key
删除 Redis Key
查看 MQ
查看 Robot
```

------------------------------------------------------------------------

# 59. 验收标准

系统达到以下条件才认为 V1 完成：

1.  Docker Compose 一条命令可以启动；
2.  不依赖额外人工部署数据库；
3.  Site 配置重启后不会丢失；
4.  可以添加多个 Server；
5.  可以添加多个 Redis；
6.  可以添加多个 Artemis；
7.  可以添加多个 Robot；
8.  用户切换 Site 后所有模块自动切换；
9.  Server 查询失败不会导致平台异常；
10. Redis 查询不会使用 KEYS \*；
11. Redis 危险操作需要二次确认；
12. 所有修改/删除操作都有 Audit Log；
13. 外部连接都有 timeout；
14. 不存在无限 retry；
15. 多用户同时查询不会产生大量重复 SSH；
16. 平台自身资源占用保持较低；
17. 敏感密码不直接返回前端；
18. 可以通过 Docker Volume 保证平台配置持久化。

------------------------------------------------------------------------

# 60. 最终目标

这个平台最终不是：

> "又一个 Grafana。"

而应该是：

> **一个内部工程人员遇到服务器 / Redis / MQ / Robot
> 问题时，第一时间打开的统一诊断入口。**

理想操作路径：

``` text
打开平台
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

最终核心体验：

> **少输入、少等待、少切系统、快速定位问题。**
