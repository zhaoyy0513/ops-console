# Implementation Plan: Ops Console V1（内部服务器运维诊断平台）

来源文档：`docs/prd-tech-design-v0.2.md` · 拆解日期：2026-09-21
任务清单（含验收标准）：`tasks/todo.md` · 无外部 tracker，以 todo.md 为准

## Overview

轻量内部运维诊断平台：Vue 3（模块注册式）+ FastAPI（模块注册式）+ 现有 Redis（配置/缓存/锁/日志）+ Docker Compose（backend + ops-nginx）。按 PRD §31 的 12 个 Phase 顺序垂直切片，每个模块交付"provider + API + 前端页面"完整路径。

## Architecture Decisions（继承 PRD，约束所有任务）

- **模块注册机制（前后端同标准）**：新增模块 = 新增目录 + 一行注册，不改核心代码（验收 17/18）。
- **Adapter First**：业务层不直接依赖 SSH/Redis/Jolokia/HTTP 协议实现，统一走 provider。
- **平台 Redis 与业务 Redis 严格隔离**：`OPS_REDIS_URL` 连接由 `core/redis.py` 独占；业务 Redis 连接由 redis 模块 provider 按配置创建，严禁混用（PRD §17.1）。
- **Server 只读**：无任何 SSH 操作入口，后端仅白名单命令（验收 8）。
- **Redis 唯一可写**：SCAN 禁 KEYS、危险命令黑名单、写操作记 oplog、删除 5 秒倒计时（UI 防误操作，非安全机制）。
- **无用户体系**：无登录/RBAC，oplog 无用户字段。
- **按需查询 + 短 TTL 缓存 + 锁合并**：不做长连接、WebSocket、Prometheus。

## 对 PRD §31 顺序的偏差（依赖驱动）

1. `core/oplog.py` 提前到 Phase 1（T04）：Redis 写操作（Phase 6）与 Overview 最近操作（Phase 9）都依赖它。
2. APScheduler 提前到 MQ 趋势采样任务（T22）：首次消费方出现时引入，不做独立框架任务。

## Task List（顺序索引，详情见 todo.md）

### Phase 1 基础工程 + 模块注册框架
- T01 仓库结构重组（backend/ + frontend/）与依赖安装
- T02 后端 core 基础设施（config / 平台 Redis / 缓存+锁 / 统一错误 / 超时 / 信号量）
- T03 后端模块注册机制 + demo 模块
- T04 操作日志 core（LPUSH+LTRIM，保留 1000 条）
- T05 前端骨架 + 模块注册机制（registry / 动态路由 / site store / demo 模块）

**Checkpoint 1**：前后端可启动；demo 模块两端均"一行注册"生效；pytest 通过。

### Phase 2 Site 管理
- T06 Sites CRUD API（密码不回显 / 留空不改）
- T07 站点资源配置 CRUD（servers / redis / mq / robots）
- T08 配置导出 / 导入 JSON
- T09 前端站点管理 + Site 切换器
- T10 连接测试框架（POST /api/test-connection 分发 + ResourceTestButton）

**Checkpoint 2**：UI 建站配资源、导出导入 roundtrip、pytest 全绿。

### Phase 3-4 Server（只读诊断）
- T11 SSH Provider（白名单聚合命令 + 解析器）
- T12 Server API（缓存 + 锁合并 + 超时 + test 接入）
- T13 诊断引擎（全局默认阈值）
- T14 阈值覆盖（资源 > 站点 > 全局）
- T15 前端 Server 模块

**Checkpoint 3**：真实/模拟主机出指标与诊断色；Server 页无任何写入口。

### Phase 5-6 Redis（唯一可写）
- T16 目标 Redis Provider + Info + 连接测试
- T17 SCAN 浏览 + Key 详情（5 类型 / TTL / Memory）
- T18 操作 API + 危险命令拒绝 + oplog
- T19 前端 Redis 浏览器（DB / 搜索 / 详情）
- T20 前端 Redis 编辑与删除（类型化编辑 / 确认框 / 5 秒倒计时）

**Checkpoint 4**：SCAN 无 KEYS；编辑、倒计时删除、危险命令拒绝、oplog 全部可验证。

### Phase 7-8 MQ / Robot
- T21 ArtemisProvider（Jolokia）
- T22 MQ API + 诊断 + backlog 趋势采样（引入 APScheduler）
- T23 前端 MQ 模块
- T24 RobotProvider + API + 连接测试
- T25 前端 Robot 模块

### Phase 9 Overview
- T26 后台健康检查 job（30 秒）
- T27 Overview API（聚合健康 / 异常摘要 / 最近 20 操作）
- T28 前端 Overview 模块

### Phase 10 操作日志页 + 稳定性
- T29 Audit API + 前端操作日志页
- T30 稳定性收尾（重试上限 / 并发信号量 / 超时全覆盖 / 错误包络扫尾）

### Phase 11 部署
- T31 Docker Compose（backend + ops-nginx，宿主机 8090）

### Phase 12 测试与验收
- T32 测试补全 + E2E 主路径
- T33 扩展性验证 demo（前后端各加一个 database 存根模块，仅注册不改核心 → 验收 17/18）

## Parallelization

- 可并行：T02-T04（后端 core）与 T05（前端骨架）；各资源模块的前端任务在 API 契约冻结后可并行（T15 / T19-20 / T23 / T25 / T28）。
- 必须串行：T06→T07→T08（同一模块存储层）；T16→T17→T18；T31 依赖全部功能任务。
- 契约先行：`/api/test-connection` 响应结构与统一错误包络在 T10 前冻结，之后四个模块并行填充实现。

## Risks and Mitigations

| 风险 | 影响 | 缓解 |
|------|------|------|
| Artemis 2.19 Jolokia 访问方式/认证与现场不符 | High | T21 先做连通性探测，解析器用现场抓取的 JSON 样本做单测 |
| Linux 发行版命令输出差异导致解析错误 | Medium | 解析器按固定样本测试 + 字段缺失时返回 Unknown 而非报错 |
| Windows 开发机无真实 SSH/Redis 目标 | Medium | 单测全走 fixture/fakeredis；集成验证列为手动步骤 |
| Robot API 数据格式未知（PRD 未给 schema） | Medium | T24 前向用户要样例响应；provider 做字段映射层隔离 |
| 导出 JSON 是否含明文密码未定 | Low | 默认含（否则导入后无法连接）；见 Open Questions |
| 调度器多实例重复采样 | Low | V1 单实例部署，`ponytail:` 注释标注上限 |

## Open Questions（不阻塞拆解，实施前确认）

1. Robot HTTP API 的真实响应格式样例？（T24 前需要）
2. 现场 Artemis Jolokia 的认证方式与端口？（T21 前需要）
3. 配置导出 JSON 是否包含明文密码？（建议包含，内部工具 + 导入可用性优先）
4. 阈值覆盖的管理入口放站点编辑页还是独立设置页？（T14/T15 时定，建议站点编辑页内嵌）
