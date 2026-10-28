# Page/Knowledge 拆分 + 三主题切换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Page 归页面（pages 资源恢复 + 页内 CRUD），Knowledge 归知识库（独立后端模块、纯 tab 管理、拖拽上传、编辑仅名称）；CountdownConfirm Teleport 根修；三主题（neon/holo/synth）圆点切换。

**Architecture:** 后端 sites 回退 `pages` 两档 + 反向迁移；新增 `modules/knowledge/`（自有路由/存储/oplog）。前端恢复 `modules/page/`、重写 `modules/knowledge/`；主题走 `data-theme` 三值 token 块 + 侧栏圆点。

**Tech Stack:** FastAPI + pydantic / Vue 3 + shadcn-vue + Tailwind v4 + marked + dompurify；测试 pytest+fakeredis / vitest。

**Spec:** `docs/superpowers/specs/2026-10-28-page-knowledge-split-design.md`（含追加需求段）

---

### Task 1: 后端 — sites 回退 pages + 反向迁移 + knowledge 独立模块（TDD）

**Files:**
- Modify: `backend/app/modules/sites/api.py`（KnowledgeConfig→PageConfig 两档；保留 _update_model metadata 修复）
- Modify: `backend/app/modules/sites/service.py`（RESOURCE_TYPES 回 pages；_with_kind 两档；迁移函数改反向）
- Modify: `backend/app/modules/sites/__init__.py`（挂钩改调新迁移函数）
- Modify: `backend/tests/test_resources_api.py`、`backend/tests/test_knowledge_migration.py`（回改 + 反向用例）
- Create: `backend/app/modules/knowledge/{__init__,api,service}.py`
- Create: `backend/tests/test_knowledge_docs.py`
- Modify: `backend/app/modules/__init__.py`（_MODULES 注册 knowledge）

**Steps:**
1. 改测试先红：test_resources_api 恢复 pages 两档用例（url/html，撤 markdown 用例）；test_knowledge_migration 改反向四用例（仅 knowledge→RENAME 回 pages；并存合并 pages 为准；仅 pages noop；不再需要旧导出 pages 兼容用例——该兼容逻辑从 import_all 删除）。
2. sites 回退实现：PageConfig（url/html 二选一，原 validators 原文恢复）、RESOURCE_TYPES、_with_kind 两档；`migrate_knowledge_back_to_pages`（结构同现函数，方向反转：src=knowledge hash, dst=pages hash）；`__init__.py` 换函数名。**`_update_model` 的 Annotated metadata 重建保留不动**（PageConfig 的 url/html validators 由此在编辑路径同样生效——测试保留一条 PUT 超长 url/非法 url 的 422 断言）。
3. 新模块 `knowledge`：api.py 定义 DocIn/DocUpdate（metadata 语义同构小函数在本模块实现）+ 四路由；service.py `KNOWLEDGE_KEY = "ops:knowledge:{site_id}"` hash CRUD + 同站 name 唯一 + oplog（resource `knowledge/{name}`，action `KNOWLEDGE_CREATED/UPDATED/DELETED`）；站点校验用 `sites.service.site_key` + 平台 Redis hexists。`_MODULES` 注册。
4. 新测试 `test_knowledge_docs.py`：CRUD 四动词、name 唯一 409、1M 上限创建/编辑双 422、站点不存在 404、oplog 断言。
5. 全量 `uv run pytest backend/tests -q` 全绿 → commit。

### Task 2: CountdownConfirm Teleport 根修

**Files:** Modify `frontend/src/components/CountdownConfirm.vue`、`frontend/src/components/CountdownConfirm.test.ts`

**Steps:**
1. AlertDialog（Overlay + RContent）包 `<Teleport to="body">`；触发按钮留在原位。注释更新（玻璃主题 backdrop-filter 破坏 fixed 定位前提，teleport 回视口基准）。
2. 测试适配：断言弹窗挂载 body（teleport 后 `mount` 返回的 wrapper 需从 `document.body` 查询）。
3. `npx vitest run` 全绿 → commit。

### Task 3: 前端 — Page 模块恢复 + sites 前端回退

**Files:** Create `frontend/src/modules/page/{index,api,PageView,PageDialog}.vue*`（由现 knowledge 模块裁剪）；Modify `frontend/src/modules/index.ts`、`layouts/MainLayout.vue`（icons）、`modules/sites/{api.ts,SiteResourcesDrawer.vue,ResourceEditModal.vue}`（回退 pages）、`i18n/index.ts`（page.* 恢复+页内 CRUD 文案）、`i18n/help.ts`；Delete `modules/sites/knowledgeForm.ts(+test)`；Delete `modules/knowledge/` 旧三文件中本任务范围外不动（Task 4 重写，本任务不碰 knowledge 目录）。

**Steps:**
1. PageView/PageDialog 由现 KnowledgeView/KnowledgeDialog 复制裁剪：撤 markdown 类型/上传/粘贴图/阅读渲染分支；kind 两档；PageDialog = name/description/url/html 二选一 + .html 上传（抽屉原能力，i18n key 归 page.*）。
2. api.ts：PageResource（kind 'url'|'html'）+ pageApi 四方法 + derivePageKind。
3. sites 前端回退：ResourceType/URL_SEGMENT/TYPES(label 'Page')/COLUMN_DEFS/ResourceEditModal 恢复 pages 二选一（撤 markdown 提示、三选一、drawerMdHint）；knowledgeForm.ts+test 删除，二选一校验回归 save() 内联。
4. registry：page order 3 恢复；orders 重排 knowledge 4、redis 5、mq 6、device 7、ssh 8、database 9；MainLayout MODULE_ICONS page→DocumentTextOutline。
5. i18n：page.* 恢复（title 页面/Page + kindUrl/kindHtml + new/edit/open/del/saved/deleted/needOne/empty/hintShort + htmlInvalid/htmlLoaded/uploadHtml/htmlPh/urlPh/frameNote/fullscreen 等）；help.ts page 主题重写（含页内 CRUD 说明）。
6. `npm run build` + `npx vitest run` 绿 → commit。

### Task 4: 前端 — Knowledge 模块重建（文档 + 拖拽 + 仅名称编辑）

**Files:** Rewrite `frontend/src/modules/knowledge/{index,api}.ts`、`KnowledgeView.vue`、`KnowledgeDialog.vue`；Modify `i18n/index.ts`（knowledge.* 聚焦文档）、`i18n/help.ts`；Create `frontend/src/modules/knowledge/knowledge.test.ts`（deriveDoc 无——本模块无 kind 派生，改测拖拽文件分类纯函数 `classifyDropFiles`）。

**Steps:**
1. api.ts：`KnowledgeDoc {id,name,description,markdown,enabled}` + knowledgeApi（`/knowledge/${siteId}` list/create/update/remove）。
2. KnowledgeDialog：create 模式（name/description/markdown 编辑器 + .md 上传 + 粘贴图 + 上传图片按钮生成独立图片文档）与 edit 模式（仅 name，PUT 只带 {name}）；拖放进编辑器 = 同粘贴语义。
3. KnowledgeView：卡片墙 + 遮罩（打开=阅读弹窗/编辑=改名/删除）+ 新建；**整域 dropzone**：drop .md/图片 → 预填新建弹窗（纯函数 `classifyDropFiles(files): {markdownText, images, names}` 导出供测试）；拖入高亮。
4. 阅读弹窗：现有 marked+DOMPurify + sandbox 壳新标签管线原样保留。
5. i18n knowledge.* 重写为文档域文案；help.ts knowledge 主题重写。
6. build + vitest 绿 → commit。

### Task 5: 主题系统三选一（neon/holo/synth）

**Files:** Rewrite `frontend/src/styles/tokens.css`（三主题 token 块）、`frontend/src/stores/theme.ts`、`layouts/MainLayout.vue`（删明暗按钮 + footer 圆点）、`style.css`（[data-theme] 作用域标题外发光）、`i18n/index.ts`（layout.themes tooltips）。

**Steps:**
1. tokens.css：删除 light/dark 两块，写三块。每块含全套 shadcn 变量 + `--ops-*` + `--ops-aurora`（多层背景：极光径向 + [neon/synth 的网格线 repeating-linear-gradient] + 底色）+ `--ops-shadow-card`（多层投影含光晕/顶部高光）+ `--ops-card-border` + `--ops-gradient-text`。色值按 spec 追加段。
2. theme store：`OpsTheme = 'neon'|'holo'|'synth'`，默认 neon，LEGACY `{light:'holo', dark:'neon', mono:'neon', terminal:'neon'}`。
3. MainLayout：header 删 Sun/Moon 按钮；sider-footer 分割线下、版本号上加 3 圆点（渐变底色 inline style，active ring，title=i18n tooltip）。
4. style.css：`[data-theme='neon'] .ops-gradient-text { text-shadow: 0 0 18px rgba(0,245,255,.35) }`（synth 同款粉光晕；holo 无）。
5. build + vitest 绿 → commit。

### Task 6: 收尾

build-stamp 更新；`uv run pytest backend/tests -q` + `npx vitest run` + `npm run build` 三绿；最终整体审查（spec 端到端 + 跨任务一致性 + 遗留台账）。

---

## Self-Review 记录

- Spec 覆盖：回退/反向迁移/独立模块/拖拽/仅名称编辑/图片卡/Teleport 根修/三主题圆点——均有任务对应；「明确不做」未实现。
- 类型一致性：`PageResource`/`pageApi`/`derivePageKind`（T3）与 `KnowledgeDoc`/`knowledgeApi`/`classifyDropFiles`（T4）各自闭环；迁移函数名 `migrate_knowledge_back_to_pages` T1 内定义与挂钩一致。
- 顺序约束：T1∥T2（文件不相交）→ T3 → T4（i18n/registry 与 T3 串行）→ T5（MainLayout/tokens 串行）→ T6。
