# Page 与 Knowledge 拆分设计

日期：2026-10-28（第二轮，取代同日第一版 knowledge 模块设计）　分支：feature/v2.0.0

## 背景与问题

第一版把 `pages` 资源整体更名为 `knowledge` 并塞进 url/markdown/html 三类，导致「页面」与「知识库」概念混淆；且玻璃主题的 `Card` `backdrop-filter` 打破了 CountdownConfirm「祖先无 filter」的定位前提，**全站卡片内的删除确认弹窗定位损坏**（Redis/MQ/Server/知识库四处受影响）。

## 目标

1. **Page（页面）归页面**：url 链接 + HTML 页卡片墙；资源类型改回 `pages`，站点资源抽屉恢复 Page 入口；Page 视图保留 hover 遮罩（打开/编辑/删除）与页内「新建」。
2. **Knowledge（知识库）归知识库**：只有 Markdown 文档；**独立后端模块**（用户决策），不进资源抽屉，增删改查全在 tab 内完成；图片 = 正文粘贴内嵌 + 独立图片卡（上传图片自动生成 `![](…)` 文档，用户决策）。
3. 删除确认弹窗 Teleport 根修（全站受益）。
4. 存量测试数据反向迁移回 `pages`（用户决策），知识库空启动。

## 决策记录

| 决策点 | 结论 |
|---|---|
| 知识库后端 | 独立模块 `backend/app/modules/knowledge/`（自有路由/存储/oplog） |
| 存量数据 | 启动反向迁移 `ops:site:{sid}:knowledge` → `pages` |
| 图片形态 | 编辑器粘贴/上传内嵌正文 + 「上传图片」生成独立图片文档 |
| 文档存储 | Redis hash `ops:knowledge:{site_id}`（field=id, value=JSON），单篇 markdown 1M 字符上限，图片 base64 内嵌（视频等大文件 future 另立文件存储） |
| 弹窗修复 | CountdownConfirm 弹窗部分 `<Teleport to="body">`（根修，全站生效） |

## 后端

### sites 模块回退（`backend/app/modules/sites/`）

- `RESOURCE_TYPES`：`knowledge` → `pages`；`KnowledgeConfig` → `PageConfig`（url/html 二选一，撤 markdown 字段与相关 validator；`_with_kind` 回两档 url/html）。
- **保留** `_update_model` 的 Annotated metadata 重建（PUT 路径校验生效是真实改进，与本轮拆分无关）。
- 迁移函数改为反向 `migrate_knowledge_back_to_pages`：仅源（knowledge）存在 → RENAME 为 pages；并存 → pages 缺失 id 从 knowledge 并入（pages 为准）后删源；仅 pages → 不动。lifespan 兜底（try/except + loguru）同现有模式。
- 抽屉/编辑弹窗相关后端无独立改动（通用 CRUD 自动跟随资源类型名）。

### 新模块 `backend/app/modules/knowledge/`

- `api.py`：`DocIn`（name 必填、description 选填、markdown 空白归 None + Annotated 1M 字符上限、enabled 默认 true）+ `DocUpdate`（全可选，复用 `_update_model` 同款 metadata 语义——在本模块内实现同构小函数，不从 sites import 私有物）。路由（tag knowledge）：
  - `GET /knowledge/{site_id}` 列表（按 id 排序，enabled 过滤交给前端）
  - `POST /knowledge/{site_id}` 201；`PUT /knowledge/{site_id}/{doc_id}`；`DELETE ...` 204
- `service.py`：hash key `ops:knowledge:{site_id}`；create/update/delete；同站点 name 唯一；oplog `knowledge/{name}` + `KNOWLEDGE_CREATED/UPDATED/DELETED`；站点存在性校验用 `sites.service.site_key` 公开函数 + 平台 Redis hexists（不 import 私有物）。
- `__init__.py`：`register_module`；注册进 `modules/__init__.py::_MODULES`。
- 不进 sites export/import（文档为可重建内容；备份覆盖是已知边界，future 需要再补）。
- 测试 `backend/tests/test_knowledge_docs.py`：CRUD 四动词、name 唯一 409、1M 上限 422（创建+编辑双路径）、站点不存在 404、oplog 记录。

## 前端

### CountdownConfirm 根修（`components/CountdownConfirm.vue`）

AlertDialog（Overlay + Content）包 `<Teleport to="body">`：fixed 定位回归视口基准，玻璃 Card 的 backdrop-filter 不再影响任何视图。测试适配 teleport 断言。

### `modules/page/`（恢复）

- `index.ts`：id/title/routePath = page/Page/page，order 3，icon document-text-outline。
- `api.ts`：`PageResource`（kind: 'url'|'html'|null）+ `pageApi`（`/sites/{id}/pages` CRUD）+ `derivePageKind` 两档镜像。
- `PageView.vue`：现 KnowledgeView 裁剪 markdown 而来——卡片墙 + hover 遮罩（打开/编辑/删除 + 新建按钮）+ 阅读弹窗（html → sandbox iframe；url → 新标签）。
- `PageDialog.vue`：url/html 二选一表单 + .html 上传（原抽屉能力搬进页内弹窗）。

### `modules/knowledge/`（重写为文档模块）

- `index.ts`：id/title/routePath = knowledge/Knowledge/knowledge，order 4，icon book-outline。
- `api.ts`：`KnowledgeDoc`（id/name/description/markdown/enabled）+ `knowledgeApi`（`/knowledge/{siteId}` CRUD）。
- `KnowledgeView.vue`：卡片墙 + 同款 hover 遮罩 + 新建按钮 + 阅读弹窗（marked+DOMPurify 内联渲染 + sandbox 壳新标签——现有管线整体保留）。
- `KnowledgeDialog.vue`：name/description/markdown 编辑器 + .md 上传 + 粘贴图片（压缩插入光标，现有逻辑）+ **「上传图片」按钮**（选图 → 压缩 → 正文生成 `![](data:…)`；name 为空自动取文件名去扩展名 → 保存即独立图片文档）。

### 收尾

- `MainLayout` MODULE_ICONS：page → DocumentTextOutline（恢复）、knowledge → BookOutline；各模块 order 重排（page 3、knowledge 4、redis 5、mq 6、device 7、ssh 8、database 9）。
- sites 前端回退：ResourceType/URL_SEGMENT/TYPES/COLUMN_DEFS/ResourceEditModal 恢复 pages（url/html 二选一，撤 markdown 提示与三选一）；`knowledgeForm.ts`/test 删除（二选一校验回归原内联）。
- i18n：`page.*` 恢复并补充页内 CRUD 文案（new/edit/open/del/saved/deleted/needOne/htmlInvalid/htmlLoaded/uploadHtml 等自 knowledge.* 迁来）；`knowledge.*` 聚焦文档（title 知识库 + 文档编辑/阅读文案）；help.ts 两主题分写；build-stamp 更新。
- registry.test 等前端既有测试跟随。

## 测试门槛

- 后端：pytest 全绿（pages 两档用例恢复、反向迁移用例、knowledge docs 新用例）。
- 前端：vitest 全绿（CountdownConfirm teleport 适配、derivePageKind、registry 等）。
- 冒烟：删除确认弹窗在 Page/Redis/MQ/Server 四处均全屏居中；Page 页内新建链接/HTML；知识库新建文档/图片卡、粘贴图、阅读、深色主题；抽屉 Page 入口可用且无 knowledge 条目。

## 明确不做

知识库进 export/import 备份（future）、视频/大文件存储（future 立项）、知识库多级目录/标签。

## 追加需求（同日用户补充）

### 知识库交互补充

- **拖拽上传**：知识库视图整域为 dropzone——拖入 `.md` 读为正文、拖入图片压缩后生成 `![](data:…)`，预填「新建」弹窗（name 取文件名去扩展名，多图按序追加）；弹窗内编辑器同样接受拖放（语义同粘贴，插入光标处），拖入时显示高亮提示。
- **编辑仅名称**：文档创建后内容不可改——编辑弹窗只有名称字段（PUT 只提交 `{name}`，后端全可选 update 语义天然支持）；描述与正文仅在创建时录入。操作集 = 重命名 / 删除 / 查看。
- **markdown 回显与图片展示**：沿用现有管线（marked + DOMPurify 内联渲染，prose 样式 img 自适应；纯图片文档即一张居中大图），新标签走 sandbox 壳。

### 主题系统重做（取代现有明暗二态）

- 三套完整主题，token 骨架共用，`data-theme` 三值：`neon`（默认）/ `holo` / `synth`。
  - **neon 深色霓虹玻璃**：基底 #0B1020，青/紫/品红对角极光（#00F5FF/#7C3CFF/#FF2BD6）+ 极细青网格线 rgba(0,245,255,0.06)；卡片 rgba(20,25,45,0.55) + blur 16px + 霓虹光边与深投影；状态点 #00F5AA；渐变标题 #00F5FF→#7C3CFF→#FF2BD6 带微外发光；正文冰白 #E9F1FF。
  - **holo 全息幻彩浅色**：基底 #F8FAFF，五色幻彩径向（#FFD6F2/#D6F0FF/#E8FFE0/#F0E4FF/#FFF4D6）；卡片 rgba(255,255,255,0.7) + 淡紫投影；渐变标题 #FF2BD6→#7C3CFF→#00C2FF。
  - **synth 复古落日**：基底 #12002B，底部落日径向（#FF3D81→#FFB703）+ 青色电光光晕 + 细网格；卡片 rgba(18,0,43,0.6) 粉描边光晕；渐变标题 #FF3D81→#FFB703；状态点 #00FF9D。
- theme store：`OpsTheme = 'neon'|'holo'|'synth'`，默认 neon，localStorage 旧值兼容（light→holo、dark→neon）。
- 切换 UI：侧栏 footer 分割线下、版本号上，3 个渐变圆形圆点（各主题配色微缩），active 高亮环 + i18n tooltip；header 现有明暗切换按钮删除。
- 玻璃卡片泛光/网格线等主题差异全部收敛进 token（`--ops-aurora` 多层背景、`--ops-shadow-card` 多层投影含光晕）+ 个别 `[data-theme]` 作用域规则（标题外发光）。
