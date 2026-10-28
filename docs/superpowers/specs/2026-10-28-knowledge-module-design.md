# 知识库（Knowledge）模块设计

日期：2026-10-28　分支：feature/v2.0.0

## 背景与目标

现有 `Page` 模块是只读卡片墙：展示站点级 `pages` 资源（url 外链 / 内联 HTML 二选一），增删改全在站点配置抽屉里。本次改造：

1. **彻底移除 Page 概念**——前端模块、后端模型、资源类型 key、路由、i18n 命名空间全部改名，不留 `page`/`Page`/`pages` 字样。
2. 新增 **Markdown 文档**类型：上传 .md 或粘贴文本，应用内阅读；粘贴图片自动压缩为 base64 内嵌。
3. 增删编辑搬进知识库页面：卡片墙头部「新建」按钮；卡片 hover 遮罩三按钮（打开 / 编辑 / 删除）。
4. 删除卡片右上角冗余的全屏（站内预览）图标。

不在范围（明确不做）：视频上传（需真实文件存储，后续单独立项）、独立附件存储体系（图片走 base64 内嵌）、oplog 新增埋点（通用资源 CRUD 已自动记录 `RESOURCE_CONFIG_*`）。

## 命名与全局重命名映射

| 位置 | 旧 | 新 |
|---|---|---|
| 后端资源类型 key（Redis hash 尾段 / RESOURCE_TYPES / 路由段 / oplog resource） | `pages` | `knowledge` |
| 后端 Pydantic 模型 | `PageConfig` | `KnowledgeConfig` |
| 后端 API 路由 | `/sites/{site_id}/pages` | `/sites/{site_id}/knowledge`（URL_SEGMENT 缺省即资源类型名，零配置） |
| kind 派生值 | `url` / `html` | `url` / `markdown` / `html` |
| 前端模块目录 / id / routePath | `page` | `knowledge`（`/console/site/:siteId/knowledge`） |
| 前端视图 / 类型 / api 名 | `PageView.vue` / `PageResource` / `pageApi` | `KnowledgeView.vue` / `KnowledgeResource` / `knowledgeApi` |
| i18n 命名空间 | `page.*` | `knowledge.*`（含 sites 抽屉里引用的 `page.*` 文案） |
| help 主题 | `page` | `knowledge` |
| 模块显示名 | Page | zh 知识库 / en Knowledge |

## 数据模型与存储

存储不变：仍是 Redis 站点资源 Hash（`ops:site:{site_id}:knowledge`，field=id，value=JSON），走 sites 通用资源 CRUD，`KnowledgeConfig` 三选一校验：

```python
class KnowledgeConfig(BaseModel):
    id: str | None
    name: str
    description: str = ""
    url: str | None      # 链接型
    markdown: str | None # 文档型，validator：非空白按文本收，上限 1_000_000 字符
    html: str | None     # HTML 型（保留原 validator）
    enabled: bool = True
```

- `model_validator`：url / markdown / html 至少其一非空白。
- kind 是读取时派生字段（`_with_kind`），不落存储：有 `url` → `url`；有 `markdown` → `markdown`；否则 `html`。存量数据零迁移成本。
- 单篇 markdown 上限 1MB：纯文本绰绰有余；图片内嵌后单图压缩目标 <300KB（1280px / JPEG 0.8），超限由后端 validator 拒绝并原话报错。

## 存量数据迁移

Redis hash key 改名 `ops:site:{sid}:pages` → `ops:site:{sid}:knowledge`：

- **启动迁移**：后端启动时（sites 模块注册处）遍历 `ops:sites` 集合，对每个站点：
  - 仅源存在 → `RENAME`（原子，一行）。
  - 源目标并存（降级运行期间旧代码写过源 key）→ 逐条合并：源中目标缺失的 id 复制进目标，目标已有 id 以目标为准，然后删除源。防降级窗口写入的数据静默不可见。
  - 仅目标存在 → 不动。约 12 行。
- **导入兼容**：`import_all` 接受旧版导出文件里的 `pages` 数组，映射进 `knowledge`（拼接合并）。2 行，防止旧备份静默丢数据。

## 后端改动（全部在 `backend/app/modules/sites/`）

1. `service.py`：`RESOURCE_TYPES` 与 `_with_kind` 改名扩展；`import_all` 兼容 `pages`；启动迁移函数（`register_module` 调用）。
2. `api.py`：`PageConfig` → `KnowledgeConfig`（+`markdown` 字段与校验）；`RESOURCE_MODELS` key 改名；`sites/{site_id}/knowledge` 路由自动生效。

## 前端改动

### 模块壳（`frontend/src/modules/knowledge/`，原 `page/` 目录改名）

- `index.ts`：id / routePath / title 改 `knowledge` / `knowledge` / 知识库（i18n key）。
- `api.ts`：`KnowledgeResource{ kind: 'url'|'markdown'|'html'|null; markdown?: string }`，`knowledgeApi.list/delete/create/update` 指向 `/sites/${siteId}/knowledge`。

### KnowledgeView.vue（重写交互）

- 卡片墙头部：标题 + 「新建」按钮 + TabHelp。
- **新建/编辑弹窗**（同组件两用）：站点只读自动填当前 site；名称、描述、类型三选一（链接 / 文档 / HTML 页）；按类型渲染 URL 输入框 / Markdown 文本域 / HTML 文本域。
  - Markdown 上传：`.md`/`.markdown` 文件读为文本填入。
  - Markdown 粘贴图片：监听 paste 事件，`image/*` → canvas 压缩（1280px、JPEG 0.8）→ `![](data:image/jpeg;base64,…)` 插入光标处。
- **卡片 hover 遮罩**：半透明遮罩层 + 三按钮——左「打开」、中「编辑」、右「删除」。打开分发：url 新标签（noopener）；markdown/html 进阅读弹窗。卡片本体点击仍走「打开」（遮罩只是增补入口）。删除走现有 `CountdownConfirm` 倒计时组件。原 Maximize2 图标删除。
- **阅读弹窗**：复用现有全屏预览 Dialog。markdown 用 `marked` 解析 + `DOMPurify.sanitize` 净化后应用内渲染（`v-html`），跟随主题深浅色；html 保持现有 sandbox iframe。弹窗内全屏按钮保留（那是弹窗铺屏，与卡片图标是两回事）。

### 站点配置抽屉（`sites/ResourceEditModal.vue`）

- 类型 key `pages` → `knowledge`，标签/字段规则/默认值/i18n 引用同步改名。
- 编辑表单只保留 url / html 字段，**不含 markdown**：payload 走 `exclude_unset` 语义，抽屉提交不携带 markdown 字段则文档内容不会被抹掉；markdown 类型条目在抽屉里显示提示「文档内容请在知识库页面编辑」。

### 收尾

- `registry.test.ts` 标题断言更新；i18n 全量 zh+en、无字面花括号；`MainLayout.vue` build-stamp 更新（bMMDD-HHMM）。
- 新依赖：`marked`、`dompurify`（+ `@types/dompurify`，若需）。

## 错误处理

- markdown 超限：后端 422 原话返回，前端弹 message。
- 粘贴非图片 / 压缩失败：忽略粘贴，不阻塞输入。
- 阅读弹窗打开失败（无内容）：按钮不渲染该路径，不可能触达。
- 删除确认取消：无副作用。

## 测试

- 后端 `test_resources_api.py`：路由改名后全量过；新增 markdown 校验（超限 422、三选一、kind 派生三档）、旧 `pages` key 启动迁移、旧导出文件 `pages` 字段导入兼容。
- 前端 vitest：registry 测试更新；新建/编辑弹窗类型切换与 markdown 粘贴压缩的最小回归。
- 完成门槛：`uv run pytest backend/tests -q` + `cd frontend && npx vitest run` 双绿；真实环境冒烟知识库页（新建文档 → 粘贴图 → 阅读 → 删除）。
