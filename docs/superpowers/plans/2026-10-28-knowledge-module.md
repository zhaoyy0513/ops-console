# 知识库（Knowledge）模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Page 模块全链路更名为知识库（knowledge），新增 Markdown 文档类型（上传/粘贴 + base64 内嵌图片 + 应用内渲染），新建/编辑/删除搬进卡片墙（hover 遮罩三按钮）。

**Architecture:** 后端零新路由——复用 sites 通用资源 CRUD，`pages` 资源类型更名 `knowledge` 并加 `markdown` 字段（kind 读取时派生）；Redis key 靠启动迁移函数改名。前端 `modules/page/` 目录更名 `modules/knowledge/`，视图重写为「新建/编辑弹窗 + 卡片遮罩 + 阅读弹窗」，markdown 用 marked+DOMPurify 净化后应用内渲染。

**Tech Stack:** FastAPI + pydantic（后端）；Vue 3 + shadcn-vue + Tailwind v4 + marked + dompurify（前端）；测试 pytest+fakeredis / vitest。

**Spec:** `docs/superpowers/specs/2026-10-28-knowledge-module-design.md`

---

### Task 1: 后端 — 资源类型更名 knowledge + markdown 字段（TDD）

**Files:**
- Modify: `backend/app/modules/sites/api.py`（PageConfig→KnowledgeConfig，RESOURCE_MODELS）
- Modify: `backend/app/modules/sites/service.py`（RESOURCE_TYPES、_with_kind）
- Modify: `backend/tests/test_resources_api.py`（pages 用例改名 + markdown 用例）

- [ ] **Step 1: 改写既有 pages 测试为 knowledge 并新增 markdown 用例（先跑，确认 FAIL）**

把 `backend/tests/test_resources_api.py` 中 `test_page_resource_url_or_html_and_kind` 整体替换为（其余 `pages` 字样同步改 `knowledge`，含 176-179 行的 SAME 重名用例）：

```python
async def test_knowledge_resource_three_kinds_and_markdown(client):
    """knowledge 资源：url/markdown/html 三选一；kind 派生优先级 url > markdown > html。"""
    await _make_site(client)

    r = await client.post("/api/sites/sz-test/knowledge", json={
        "id": "k-url", "name": "Grafana", "url": "https://grafana.example.com"})
    assert r.status_code == 201
    assert r.json()["kind"] == "url"

    r = await client.post("/api/sites/sz-test/knowledge", json={
        "id": "k-md", "name": "运维手册", "markdown": "# 标题\n正文", "description": "d"})
    assert r.status_code == 201
    assert r.json()["kind"] == "markdown"

    r = await client.post("/api/sites/sz-test/knowledge", json={
        "id": "k-html", "name": "旧页", "html": "<!doctype html><html><body>x</body></html>"})
    assert r.status_code == 201
    assert r.json()["kind"] == "html"

    # 三者皆空 → 422
    r = await client.post("/api/sites/sz-test/knowledge", json={"id": "k-empty", "name": "空"})
    assert r.status_code == 422

    # markdown 超 1MB → 422
    r = await client.post("/api/sites/sz-test/knowledge", json={
        "id": "k-big", "name": "大文档", "markdown": "x" * 1_000_001})
    assert r.status_code == 422

    # 1MB 边界内可存
    r = await client.post("/api/sites/sz-test/knowledge", json={
        "id": "k-edge", "name": "边界", "markdown": "x" * 1_000_000})
    assert r.status_code == 201

    # url 优先于 markdown（派生）
    r = await client.post("/api/sites/sz-test/knowledge", json={
        "id": "k-both", "name": "双填", "url": "https://a.b", "markdown": "# m"})
    assert r.json()["kind"] == "url"

    # kind 不落存储
    raw = await get_platform_redis().hget(resource_key("sz-test", "knowledge"), "k-md")
    assert "kind" not in json.loads(raw)
    listed = (await client.get("/api/sites/sz-test/knowledge")).json()
    assert {p["id"]: p["kind"] for p in listed} == {
        "k-url": "url", "k-md": "markdown", "k-html": "html",
        "k-edge": "markdown", "k-both": "url"}

    # 编辑：切换类型（markdown → url）后 kind 跟随
    r = await client.put("/api/sites/sz-test/knowledge/k-md",
                         json={"url": "https://new.example.com", "markdown": ""})
    assert r.json()["kind"] == "url"
```

文件顶部 import 行确认已有 `from backend.app.core.redis import get_platform_redis`（若无则补）。

- [ ] **Step 2: 跑测试确认 FAIL（路由 404 / import 报错）**

Run: `uv run pytest backend/tests/test_resources_api.py -q`
Expected: FAIL（`/knowledge` 404）

- [ ] **Step 3: 实现 KnowledgeConfig（api.py）**

`PageConfig` 类整体替换为（docstring 同步换；`_validate_url`、`_validate_html` 原样保留搬入）：

```python
_MD_MAX = 1_000_000


class KnowledgeConfig(ResourceBase):
    """知识库资源：链接（url）/ Markdown 文档（markdown）/ HTML 页（html）三选一。
    markdown 以 base64 内嵌图片（前端压缩后写入），上限 1MB 防配置膨胀。"""

    description: str = ""
    url: str | None = None
    markdown: str | None = None
    html: str | None = None

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("markdown")
    @classmethod
    def _validate_markdown(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        if len(v) > _MD_MAX:
            raise ValueError("markdown exceeds 1MB limit")
        return v

    @field_validator("html")
    @classmethod
    def _validate_html(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        # 明显不是 HTML 的（如粘贴了纯文本/JSON）直接拒，避免渲染出空白页
        if len(v) < 20 or ("<" not in v and "&lt;" not in v):
            raise ValueError("html must be an HTML document")
        return v

    @model_validator(mode="after")
    def _need_one_content(self) -> "KnowledgeConfig":
        # 只填了空串/空白的字段等同于都没填
        if not (self.url or self.markdown or self.html):
            raise ValueError("knowledge item requires url, markdown or html")
        return self
```

`RESOURCE_MODELS` 中键 `"pages": PageConfig` → `"knowledge": KnowledgeConfig`。路由段缺省即资源类型名，`/sites/{site_id}/knowledge` 自动生效。

- [ ] **Step 4: 实现 service.py 更名**

`RESOURCE_TYPES` → `("servers", "knowledge", "redis", "mq", "devices")`；`_with_kind` 替换为：

```python
def _with_kind(res_type: str, item: dict) -> dict:
    """knowledge 资源的派生字段 kind：url > markdown > html 三档。

    存储不落 kind（后端/前端都可能写配置），读取时按当前内容派生——
    老数据与手改数据同样得到正确分类，零迁移成本。其他资源类型原样返回。
    """
    if res_type == "knowledge":
        item["kind"] = ("url" if item.get("url")
                        else "markdown" if item.get("markdown")
                        else "html" if item.get("html") else None)
    return item
```

- [ ] **Step 5: 跑测试确认 PASS**

Run: `uv run pytest backend/tests/test_resources_api.py -q`
Expected: PASS（全文件）

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/sites backend/tests/test_resources_api.py
git commit -m "feat!: pages 资源更名为 knowledge + markdown 文档字段（1MB 上限、三选一校验）"
```

---

### Task 2: 后端 — Redis key 启动迁移 + 旧导出导入兼容（TDD）

**Files:**
- Modify: `backend/app/modules/sites/service.py`（migrate_legacy_pages、import_all）
- Modify: `backend/app/modules/sites/__init__.py`（startup 挂钩）
- Create: `backend/tests/test_knowledge_migration.py`

- [ ] **Step 1: 写迁移测试（先跑，确认 FAIL）**

新建 `backend/tests/test_knowledge_migration.py`：

```python
import json

from backend.app.modules.sites import service


async def test_migrate_renames_pages_key(fake_platform_redis):
    """旧 key 存在且目标不存在 → 原子 RENAME。"""
    r = fake_platform_redis
    await r.sadd(service.SITES_KEY, "sz-legacy")
    await r.hset(service.resource_key("sz-legacy", "pages"), "p1",
                 json.dumps({"id": "p1", "name": "旧页", "url": "https://a.b"}))
    await service.migrate_legacy_pages()
    assert json.loads(await r.hget(service.resource_key("sz-legacy", "knowledge"), "p1"))["name"] == "旧页"
    assert not await r.exists(service.resource_key("sz-legacy", "pages"))


async def test_migrate_merges_when_both_exist(fake_platform_redis):
    """降级窗口两边都有数据：源中目标缺失的 id 并入，目标已有 id 以目标为准，源删除。"""
    r = fake_platform_redis
    await r.sadd(service.SITES_KEY, "sz-both")
    await r.hset(service.resource_key("sz-both", "pages"), mapping={
        "p1": json.dumps({"id": "p1", "name": "降级期新建", "url": "https://x.y"}),
        "p2": json.dumps({"id": "p2", "name": "旧版同 id", "url": "https://old"}),
    })
    await r.hset(service.resource_key("sz-both", "knowledge"), "p2",
                 json.dumps({"id": "p2", "name": "新版同 id", "markdown": "# new"}))
    await service.migrate_legacy_pages()
    dst = service.resource_key("sz-both", "knowledge")
    assert json.loads(await r.hget(dst, "p1"))["name"] == "降级期新建"  # 源并入
    assert json.loads(await r.hget(dst, "p2"))["name"] == "新版同 id"  # 目标为准
    assert not await r.exists(service.resource_key("sz-both", "pages"))


async def test_migrate_noop_when_only_target(fake_platform_redis):
    r = fake_platform_redis
    await r.sadd(service.SITES_KEY, "sz-new")
    await r.hset(service.resource_key("sz-new", "knowledge"), "k1",
                 json.dumps({"id": "k1", "name": "新", "url": "https://a.b"}))
    await service.migrate_legacy_pages()  # 不抛错、数据不动
    assert await r.hget(service.resource_key("sz-new", "knowledge"), "k1")


async def test_import_accepts_legacy_pages_field(fake_platform_redis):
    """旧版导出文件里的 pages 数组导入后落到 knowledge。"""
    await service.import_all([{
        "id": "sz-old", "name": "旧站",
        "pages": [{"id": "p1", "name": "旧导出", "url": "https://a.b"}],
    }])
    raw = await fake_platform_redis.hget(service.resource_key("sz-old", "knowledge"), "p1")
    assert json.loads(raw)["name"] == "旧导出"
```

Run: `uv run pytest backend/tests/test_knowledge_migration.py -q`
Expected: FAIL（`migrate_legacy_pages` 不存在）

- [ ] **Step 2: 实现 service.migrate_legacy_pages + import_all 兼容**

`service.py` 资源区段（`_require_site` 之前）加：

```python
async def migrate_legacy_pages() -> None:
    """pages→knowledge 一次性迁移（应用启动时执行）：
    仅源存在 → RENAME；并存（降级窗口旧代码写过源）→ 源中目标缺失的 id 并入后删源；
    仅目标存在 → 不动。幂等：跑多次结果一致。"""
    r = get_platform_redis()
    for sid in await r.smembers(SITES_KEY):
        src = resource_key(sid, "pages")
        dst = resource_key(sid, "knowledge")
        if not await r.exists(src):
            continue
        if not await r.exists(dst):
            await r.rename(src, dst)
            continue
        target_ids = set(await r.hkeys(dst))
        merged = {rid: raw for rid, raw in (await r.hgetall(src)).items() if rid not in target_ids}
        if merged:
            await r.hset(dst, mapping=merged)
        await r.delete(src)
```

`import_all` 的 `for s in sites:` 循环体第一行（`resources = ...` 之前）插：

```python
        if "pages" in s:  # 旧版导出文件兼容：pages 数组并入 knowledge
            s["knowledge"] = s.pop("pages") + s.get("knowledge", [])
```

- [ ] **Step 3: 启动挂钩（sites/__init__.py）**

```python
from fastapi import FastAPI

from .api import router
from .service import migrate_legacy_pages


def register_module(app: FastAPI) -> None:
    """站点 + 资源配置管理模块（PRD §5/§6/§18）。"""
    app.include_router(router, prefix="/api")
    app.add_event_handler("startup", migrate_legacy_pages)
```

（httpx ASGITransport 不触发 startup，测试直接调函数；真实 uvicorn 启动时执行。）

- [ ] **Step 4: 跑迁移测试 + 全量后端测试**

Run: `uv run pytest backend/tests/test_knowledge_migration.py backend/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/sites backend/tests/test_knowledge_migration.py
git commit -m "feat: pages→knowledge Redis key 启动迁移（RENAME/合并幂等）+ 旧导出导入兼容"
```

---

### Task 3: 前端 — 模块更名 page→knowledge（壳层改名，可构建）

**Files:**
- Rename: `frontend/src/modules/page/` → `frontend/src/modules/knowledge/`
- Modify: `frontend/src/modules/knowledge/index.ts`、`api.ts`
- Modify: `frontend/src/modules/index.ts`、`frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/i18n/index.ts`、`frontend/src/i18n/help.ts`

- [ ] **Step 1: 目录与注册改名**

```bash
git mv frontend/src/modules/page frontend/src/modules/knowledge
```

`modules/knowledge/index.ts`：

```ts
import { defineOpsModule } from '../registry'
import KnowledgeView from './KnowledgeView.vue'

export default defineOpsModule({
  id: 'knowledge',
  title: 'Knowledge',
  order: 3,
  icon: 'document-text-outline',
  routePath: 'knowledge',
  view: KnowledgeView,
})
```

（本任务先把 PageView.vue 原样保留，Task 4 重写；此处 index.ts 的 import 名先改为 `import KnowledgeView from './KnowledgeView.vue'` 并同步 `git mv frontend/src/modules/knowledge/PageView.vue frontend/src/modules/knowledge/KnowledgeView.vue`。）

`modules/index.ts`：`import './page'` → `import './knowledge'`。

`MainLayout.vue`：`MODULE_ICONS` 键 `page: DocumentTextOutline` → `knowledge: BookOutline`（import 行 `DocumentTextOutline` 换成 `BookOutline`，仍从 `@vicons/ionicons5`）。

- [ ] **Step 2: api.ts 换新**

`modules/knowledge/api.ts` 整体替换：

```ts
import api from '../../api'

/** 知识库资源：链接（url）/ Markdown 文档（markdown）/ HTML 页（html）三选一。
 *  kind 读取时由后端派生：url > markdown > html。 */
export interface KnowledgeResource {
  id: string
  name: string
  description: string
  kind: 'url' | 'markdown' | 'html' | null
  url?: string | null
  markdown?: string | null
  html?: string | null
  enabled?: boolean
}

export const knowledgeApi = {
  list: (siteId: string) => api.get<KnowledgeResource[]>(`/sites/${siteId}/knowledge`),
  create: (siteId: string, data: Record<string, unknown>) =>
    api.post<KnowledgeResource>(`/sites/${siteId}/knowledge`, data),
  update: (siteId: string, id: string, data: Record<string, unknown>) =>
    api.put<KnowledgeResource>(`/sites/${siteId}/knowledge/${id}`, data),
  remove: (siteId: string, id: string) => api.delete<void>(`/sites/${siteId}/knowledge/${id}`),
}
```

- [ ] **Step 3: i18n 命名空间改名 + 文案换知识库**

`i18n/index.ts`：
1. zh `tabs.page: '页面'` → `knowledge: '知识库'`；en `tabs.page: 'Page'` → `knowledge: 'Knowledge'`。
2. zh `page: { ... }` 块（约 227 行）整块替换为：

```ts
    knowledge: {
      title: '知识库',
      hintShort: '卡片悬停出现打开/编辑/删除；链接在新标签打开',
      new: '新建',
      edit: '编辑',
      open: '打开',
      del: '删除',
      empty: '暂无内容——点击右上「新建」添加链接或文档',
      kindUrl: '链接',
      kindMarkdown: '文档',
      kindHtml: '页面',
      saved: '已保存',
      deleted: '已删除',
      imgInserted: '图片已插入（压缩为 base64）',
      siteLabel: '站点',
      nameLabel: '名称',
      descLabel: '描述',
      typeLabel: '类型',
      typeUrl: '链接',
      typeMarkdown: '文档',
      typeHtml: 'HTML 页',
      urlPh: 'https:// 开头',
      mdPh: '支持 Markdown；可直接粘贴图片（自动压缩为 base64 内嵌）…',
      htmlPh: '粘贴完整 HTML 页面内容（<!doctype html> 开头）…',
      uploadMd: '上传 .md',
      mdLoaded: '已读取 Markdown 文件内容',
      mdInvalid: '仅支持 .md / .markdown 文件',
      needName: '请填写名称',
      needOne: '请填写当前类型的内容',
      openExternal: '新标签打开',
      fullscreen: '全屏',
      exitFullscreen: '退出全屏',
      frameNote: '页面运行于隔离沙箱，无法访问本站数据',
      frameBlocked: '部分站点禁止被嵌入显示空白——请用「新标签打开」',
      drawerMdHint: '该条目为 Markdown 文档，内容请在「知识库」页面编辑',
    },
```

3. en `page: { ... }` 块（约 736 行）整块替换为：

```ts
    knowledge: {
      title: 'Knowledge',
      hintShort: 'Hover a card for open/edit/delete; links open in a new tab',
      new: 'New',
      edit: 'Edit',
      open: 'Open',
      del: 'Delete',
      empty: 'Nothing yet — use "New" to add a link or a document',
      kindUrl: 'Link',
      kindMarkdown: 'Doc',
      kindHtml: 'Page',
      saved: 'Saved',
      deleted: 'Deleted',
      imgInserted: 'Image inserted (compressed to base64)',
      siteLabel: 'Site',
      nameLabel: 'Name',
      descLabel: 'Description',
      typeLabel: 'Type',
      typeUrl: 'Link',
      typeMarkdown: 'Document',
      typeHtml: 'HTML page',
      urlPh: 'starts with https://',
      mdPh: 'Markdown supported; paste images to embed them as base64…',
      htmlPh: 'Paste a complete HTML page (starting with <!doctype html>)…',
      uploadMd: 'Upload .md',
      mdLoaded: 'Markdown file content loaded',
      mdInvalid: 'Only .md / .markdown files are accepted',
      needName: 'Name is required',
      needOne: 'Provide the content for the selected type',
      openExternal: 'Open in new tab',
      fullscreen: 'Fullscreen',
      exitFullscreen: 'Exit fullscreen',
      frameNote: 'Runs in an isolated sandbox — no access to this site’s data',
      frameBlocked: 'Some sites refuse embedding — use "Open in new tab"',
      drawerMdHint: 'This item is a Markdown document; edit its content on the Knowledge page',
    },
```

4. `grep -rn "page\." frontend/src --include=*.vue --include=*.ts`（排除 `pages`、node_modules、注释里的英文 page 一词）清点 `$t('page.` 与 `t('page.` 残留，全部改为 `knowledge.`（Task 4/5 会重写主要消费方，此处只保证无未改名引用）。

- [ ] **Step 4: help.ts 主题改名**

zh（约 59 行）`page: {` → `knowledge: {`，title `'说明 · Page'` → `'说明 · 知识库'`，lines 数组替换为：

```ts
      lines: [
        '收拢站点常用入口与文档：外链卡片一键直达，Markdown / HTML 文档站内阅读。',
        '三种类型：链接（新标签打开）、Markdown 文档（支持上传 .md 或直接粘贴，粘贴图片自动压缩为 base64 内嵌）、HTML 单文件页（沙箱隔离预览）。三者按所选类型保存。',
        '卡片悬停出现遮罩：打开 / 编辑 / 删除（删除有倒计时确认）；右上「新建」自动关联当前站点。',
        'HTML 页面运行于浏览器隔离沙箱：脚本可以执行，但无法读取本平台的登录态与数据。',
        '站点管理 → 资源 → Knowledge 仍可维护链接与 HTML 页；Markdown 文档请在知识库页面编辑。',
      ],
```

en（约 140 行）`page: {` → `knowledge: {`，title `'Instructions · Page'` → `'Instructions · Knowledge'`，lines 替换为：

```ts
      lines: [
        'Collects site entries and documents: external links one click away, Markdown / HTML docs readable in place.',
        'Three types: link (new tab), Markdown doc (upload .md or paste; pasted images are compressed and embedded as base64), single-file HTML (sandboxed preview). Only the selected type is saved.',
        'Hovering a card shows an overlay: Open / Edit / Delete (delete has a countdown confirm); "New" auto-binds the current site.',
        'HTML pages run in a browser sandbox: scripts execute but cannot read this platform’s session or data.',
        'Sites → Resources → Knowledge still manages links and HTML pages; edit Markdown docs on the Knowledge page.',
      ],
```

`TabHelp` 的 `topic` prop 消费方在 Task 4 重写视图时同步 `topic="knowledge"`。

- [ ] **Step 5: 构建通过（此时视图仍引用旧 i18n key 会丢文案但不报错；以 vue-tsc 为准）**

Run: `cd frontend && npm run build`
Expected: 构建成功（KnowledgeView 引用的 `page.*` key 已不存在会显示 key 名，Task 4 修复）

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src
git commit -m "refactor!: 前端 page 模块更名为 knowledge（目录/注册/i18n/help）"
```

---

### Task 4: 前端 — 知识库视图重写（新建/编辑弹窗 + 遮罩卡片 + Markdown 阅读）

**Files:**
- Modify: `frontend/src/modules/knowledge/KnowledgeView.vue`（整体重写）
- Create: `frontend/src/modules/knowledge/KnowledgeDialog.vue`
- Modify: `frontend/package.json`（marked、dompurify）

- [ ] **Step 1: 安装依赖**

```bash
cd frontend && npm i marked dompurify
```

（v3 起两者均自带类型，无需 @types。）

- [ ] **Step 2: 新建 KnowledgeDialog.vue（新建/编辑两用）**

```vue
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Upload } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { message } from '@/lib/message'
import { knowledgeApi, type KnowledgeResource } from './api'

const props = defineProps<{ show: boolean; siteId: string; editing: KnowledgeResource | null }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

const { t } = useI18n()
type Kind = 'url' | 'markdown' | 'html'
const kind = ref<Kind>('url')
const form = ref({ name: '', description: '', url: '', markdown: '', html: '' })
const saving = ref(false)

watch(
  () => [props.show, props.editing] as const,
  ([show, item]) => {
    if (!show) return
    kind.value = item ? item.url ? 'url' : item.markdown ? 'markdown' : 'html' : 'url'
    form.value = {
      name: item?.name ?? '', description: item?.description ?? '',
      url: item?.url ?? '', markdown: item?.markdown ?? '', html: item?.html ?? '',
    }
  },
  { immediate: true },
)

const KINDS: Array<{ key: Kind; label: string }> = [
  { key: 'url', label: 'knowledge.typeUrl' },
  { key: 'markdown', label: 'knowledge.typeMarkdown' },
  { key: 'html', label: 'knowledge.typeHtml' },
]

/** .md 单文件上传：读文本进 form.markdown（扩展名 + MIME 双判，同 .html 上传惯例） */
async function onMdFile(e: Event) {
  const input = e.target as HTMLInputElement
  const raw = input.files?.[0]
  input.value = ''
  if (!raw) return
  const name = raw.name.toLowerCase()
  if (!name.endsWith('.md') && !name.endsWith('.markdown') && raw.type !== 'text/markdown') {
    message.error(t('knowledge.mdInvalid'))
    return
  }
  try {
    form.value.markdown = await raw.text()
    message.success(t('knowledge.mdLoaded'))
  } catch (err) {
    message.error((err as Error).message)
  }
}

/** 粘贴图片 → canvas 压缩（1280px / JPEG 0.8）→ base64 data URI 插入光标处。
 *  非图片粘贴走默认行为；压缩失败静默忽略不阻塞输入。 */
async function onMarkdownPaste(e: ClipboardEvent) {
  const item = [...(e.clipboardData?.items ?? [])].find((i) => i.type.startsWith('image/'))
  if (!item) return
  const file = item.getAsFile()
  if (!file) return
  e.preventDefault()
  try {
    insertAtCursor(`![](${await compressImage(file)})`)
    message.success(t('knowledge.imgInserted'))
  } catch { /* 忽略 */ }
}

async function compressImage(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file)
  try {
    const scale = Math.min(1, 1280 / bitmap.width)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/jpeg', 0.8)
  } finally {
    bitmap.close()
  }
}

const mdArea = ref<HTMLTextAreaElement | null>(null)

function insertAtCursor(text: string) {
  const el = mdArea.value
  if (!el) {
    form.value.markdown += text
    return
  }
  const s = el.selectionStart ?? el.value.length
  const e = el.selectionEnd ?? s
  form.value.markdown = el.value.slice(0, s) + text + el.value.slice(e)
}

async function save() {
  const name = form.value.name.trim()
  if (!name) {
    message.error(t('knowledge.needName'))
    return
  }
  // 只写所选类型字段，其余置空串（后端空白视同未填；编辑切换类型不残留旧内容）
  const data = {
    name,
    description: form.value.description.trim(),
    url: kind.value === 'url' ? form.value.url.trim() : '',
    markdown: kind.value === 'markdown' ? form.value.markdown : '',
    html: kind.value === 'html' ? form.value.html : '',
  }
  if (!data.url && !data.markdown && !data.html) {
    message.error(t('knowledge.needOne'))
    return
  }
  saving.value = true
  try {
    if (props.editing) {
      await knowledgeApi.update(props.siteId, props.editing.id, data)
    } else {
      await knowledgeApi.create(props.siteId, data)
    }
    message.success(t('knowledge.saved'))
    emit('update:show', false)
    emit('saved')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog :open="props.show" @update:open="(v: boolean) => emit('update:show', v)">
    <DialogContent class="w-[560px] max-w-[92vw]" @escape-key-down.prevent @interact-outside.prevent>
      <DialogHeader>
        <DialogTitle>{{ props.editing ? $t('knowledge.edit') : $t('knowledge.new') }}</DialogTitle>
      </DialogHeader>

      <div class="grid gap-3">
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.siteLabel') }}</label>
          <!-- 站点自动匹配当前 site，只读 -->
          <Input :model-value="props.siteId" disabled />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.nameLabel') }} <span class="text-destructive">*</span></label>
          <Input v-model="form.name" />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-start gap-3">
          <label class="pt-2 text-xs text-muted-foreground">{{ $t('knowledge.descLabel') }}</label>
          <Input v-model="form.description" />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.typeLabel') }}</label>
          <div class="flex gap-1.5">
            <Button
              v-for="k in KINDS" :key="k.key"
              :variant="kind === k.key ? 'default' : 'outline'" size="sm"
              @click="kind = k.key"
            >
              {{ $t(k.label) }}
            </Button>
          </div>
        </div>

        <div v-if="kind === 'url'" class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">URL</label>
          <Input v-model="form.url" placeholder="https://" />
        </div>

        <template v-else-if="kind === 'markdown'">
          <div class="flex items-center gap-2">
            <label class="text-xs text-muted-foreground">Markdown</label>
            <label class="inline-flex cursor-pointer items-center gap-1 text-xs text-primary hover:underline">
              <Upload class="size-3.5" />
              {{ $t('knowledge.uploadMd') }}
              <input type="file" accept=".md,.markdown,text/markdown" class="hidden" @change="onMdFile">
            </label>
          </div>
          <Textarea
            ref="mdArea"
            v-model="form.markdown"
            class="min-h-[220px] font-mono text-[13px]"
            :placeholder="$t('knowledge.mdPh')"
            @paste="onMarkdownPaste"
          />
        </template>

        <template v-else>
          <div class="grid grid-cols-[90px_1fr] items-start gap-3">
            <label class="pt-2 text-xs text-muted-foreground">HTML</label>
            <Textarea v-model="form.html" class="min-h-[180px] font-mono text-[13px]" :placeholder="$t('knowledge.htmlPh')" />
          </div>
        </template>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" @click="emit('update:show', false)">{{ $t('common.cancel') }}</Button>
        <Button size="sm" :disabled="saving" @click="save">{{ $t('common.save') }}</Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
```

（`common.cancel` / `common.save` 为既有 i18n key，实现时 `grep -n "cancel\|save" frontend/src/i18n/index.ts | grep common` 核对，缺则用 `common.confirm` 或补 key。）

- [ ] **Step 3: 重写 KnowledgeView.vue**

```vue
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { ExternalLink, FileText, Link2, Maximize2, Minimize2, Pencil, Plus } from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { message } from '@/lib/message'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import EmptyState from '../../components/EmptyState.vue'
import TabHelp from '../../components/TabHelp.vue'
import FadeContent from '../../components/bits/FadeContent.vue'
import TipCopy from '../../components/TipCopy.vue'
import { useSiteStore } from '../../stores/site'
import { knowledgeApi, type KnowledgeResource } from './api'
import KnowledgeDialog from './KnowledgeDialog.vue'

const siteStore = useSiteStore()

const items = ref<KnowledgeResource[]>([])
const loading = ref(false)
const showReader = ref(false)
const active = ref<KnowledgeResource | null>(null)
const dialogShow = ref(false)
const editing = ref<KnowledgeResource | null>(null)

async function load() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    const all = await knowledgeApi.list(siteId)
    items.value = all.filter((p) => p.enabled !== false) // 停用的不进卡片墙
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => siteStore.currentSiteId, load)

const KIND_ICON = { url: Link2, markdown: FileText, html: FileText } as const

function open(p: KnowledgeResource) {
  if (p.kind === 'url' && p.url) {
    window.open(p.url, '_blank', 'noopener')
    return
  }
  preview(p)
}

function preview(p: KnowledgeResource) {
  active.value = p
  showReader.value = true
}

function openCreate() {
  editing.value = null
  dialogShow.value = true
}

function openEdit(p: KnowledgeResource) {
  editing.value = p
  dialogShow.value = true
}

/** 新标签打开（阅读弹窗脚注）：url 直开；markdown/html 转 Blob URL（快照副本，用完即回收） */
function openExternal() {
  const p = active.value
  if (!p) return
  if (p.kind === 'url' && p.url) {
    window.open(p.url, '_blank', 'noopener')
    return
  }
  const content = p.html ?? renderedMd.value
  if (!content) return
  const type = p.kind === 'markdown' ? 'text/markdown' : 'text/html'
  const blob = new Blob([content], { type: `${type};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** markdown 阅读渲染：marked 解析 + DOMPurify 净化（XSS 底线），应用内跟随主题 */
const renderedMd = computed(() => {
  if (active.value?.kind !== 'markdown' || !active.value.markdown) return ''
  return DOMPurify.sanitize(marked.parse(active.value.markdown, { async: false }) as string)
})

// ---- 阅读弹窗全屏：CSS 铺屏（同旧 PageView），Esc 关弹窗行为不变 ----
const isFullscreen = ref(false)
function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

/** 危险确认弹窗防误关（对齐 mask-closable=false） */
function blockDismiss(e: Event) {
  e.preventDefault()
}

/** 删除：倒计时确认组件的 onConfirm 回调 */
async function confirmDelete(p: KnowledgeResource | null) {
  if (!p) return
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  await knowledgeApi.remove(siteId, p.id)
  message.success(i18nT('knowledge.deleted'))
  if (deleteTarget.value?.id === p.id) deleteTarget.value = null
  await load()
}

import { useI18n } from 'vue-i18n'
const i18nT = useI18n().t

const deleteTarget = ref<KnowledgeResource | null>(null)
</script>

<template>
  <Card>
    <CardHeader class="flex-row items-center justify-between">
      <CardTitle>{{ $t('knowledge.title') }}</CardTitle>
      <span class="flex items-center gap-2">
        <span class="text-xs text-muted-foreground">{{ $t('knowledge.hintShort') }}</span>
        <tab-help topic="knowledge" />
        <Button size="sm" :disabled="!siteStore.currentSiteId" @click="openCreate">
          <Plus />
          {{ $t('knowledge.new') }}
        </Button>
      </span>
    </CardHeader>
    <CardContent>
      <div v-if="loading" class="flex justify-center py-12">
        <span class="inline-block size-6 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
      </div>
      <div v-else-if="items.length" class="page-grid">
        <fade-content v-for="(p, i) in items" :key="p.id" :delay="i * 60" class="page-fade">
          <div class="page-card" @click="open(p)">
            <div class="pc-head">
              <span class="pc-title">{{ p.name }}</span>
              <span class="pc-kind">
                <component :is="KIND_ICON[p.kind ?? 'html']" class="size-3.5" />
                <Badge size="sm" :variant="p.kind === 'url' ? 'default' : 'secondary'">
                  {{ $t(p.kind === 'url' ? 'knowledge.kindUrl' : p.kind === 'markdown' ? 'knowledge.kindMarkdown' : 'knowledge.kindHtml') }}
                </Badge>
              </span>
            </div>
            <div class="pc-desc">{{ p.description }}</div>
            <div v-if="p.kind === 'url' && p.url" class="pc-url">
              <tip-copy :text="p.url" :max="280" :copy="false" />
            </div>
            <!-- hover 遮罩：左打开 / 中编辑 / 右删除（CountdownConfirm 自带触发按钮即删除位） -->
            <div class="card-overlay">
              <button class="ov-btn" type="button" @click.stop="open(p)">
                <ExternalLink class="size-3.5" />
                {{ $t('knowledge.open') }}
              </button>
              <button class="ov-btn" type="button" @click.stop="openEdit(p)">
                <Pencil class="size-3.5" />
                {{ $t('knowledge.edit') }}
              </button>
              <span class="ov-btn ov-danger" @click.stop>
                <countdown-confirm
                  :label="$t('knowledge.del')"
                  :target="p.name"
                  :on-confirm="() => confirmDelete(p)"
                />
              </span>
            </div>
          </div>
        </fade-content>
      </div>
      <empty-state v-else :title="$t('knowledge.empty')" />
    </CardContent>
  </Card>

  <knowledge-dialog
    v-model:show="dialogShow"
    :site-id="siteStore.currentSiteId"
    :editing="editing"
    @saved="load"
  />

  <!-- 阅读弹窗：markdown 应用内渲染（净化后 v-html）；html 沿用 sandbox iframe；url 不进此弹窗 -->
  <Dialog :open="showReader" @update:open="showReader = $event">
    <DialogContent
      class="flex h-[88vh] w-[92vw] max-w-none flex-col overflow-hidden"
      :class="isFullscreen && 'page-fullscreen'"
      @escape-key-down="blockDismiss"
      @interact-outside="blockDismiss"
    >
      <DialogHeader>
        <DialogTitle>{{ active?.name ?? '' }}</DialogTitle>
      </DialogHeader>
      <div
        v-if="active?.kind === 'markdown'"
        class="md-reader min-h-0 w-full flex-1 overflow-y-auto"
        v-html="renderedMd"
      />
      <iframe
        v-else-if="active"
        class="html-frame min-h-0 w-full flex-1"
        sandbox="allow-scripts"
        :srcdoc="active.html ?? ''"
        :title="active.name"
      />
      <DialogFooter class="flex-row items-center justify-between pt-2">
        <span class="frame-note">
          {{ active?.kind === 'html' ? $t('knowledge.frameNote') : $t('knowledge.frameBlocked') }}
        </span>
        <span class="flex items-center gap-2">
          <Button variant="outline" size="sm" :title="isFullscreen ? $t('knowledge.exitFullscreen') : $t('knowledge.fullscreen')" @click="toggleFullscreen">
            <Minimize2 v-if="isFullscreen" />
            <Maximize2 v-else />
          </Button>
          <Button variant="outline" size="sm" @click="openExternal">
            <ExternalLink />
            {{ $t('knowledge.openExternal') }}
          </Button>
        </span>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.page-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.page-fade {
  display: block;
  height: 100%;
}
.page-fade :deep(.fade-content) {
  height: 100%;
}
.page-card {
  position: relative;
  height: 100%;
  min-height: 108px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 18px;
  border: 1px solid var(--ops-card-border);
  border-radius: var(--ops-radius-m);
  background: var(--ops-surface);
  backdrop-filter: blur(8px);
  cursor: pointer;
  overflow: hidden;
  transition:
    transform 200ms cubic-bezier(0.34, 1.56, 0.64, 1),
    border-color 160ms ease,
    box-shadow 200ms ease;
}
.page-card:hover {
  transform: translateY(-3px) scale(1.012);
  border-color: var(--ops-primary);
  box-shadow: 0 10px 24px rgba(31, 35, 41, 0.1);
}
@media (prefers-reduced-motion: reduce) {
  .page-card { transition: border-color 160ms ease; }
  .page-card:hover { transform: none; }
}
.pc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.pc-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ops-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pc-kind {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: none;
  color: var(--ops-text-3);
}
.pc-desc {
  font-size: 12px;
  color: var(--ops-text-2);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
.pc-url {
  margin-top: auto;
  font-size: 12px;
  color: var(--ops-text-3);
  overflow: hidden;
}
/* hover 遮罩：固定深色纱（两主题通吃）+ 三个半透明胶囊按钮；键盘 focus-within 同样显形 */
.card-overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: rgba(15, 18, 24, 0.45);
  opacity: 0;
  transition: opacity 150ms ease;
}
.page-card:hover .card-overlay,
.page-card:focus-within .card-overlay {
  opacity: 1;
}
.ov-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.55);
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  transition: background 120ms ease;
}
.ov-btn:hover {
  background: rgba(255, 255, 255, 0.25);
}
/* 删除位容器：CountdownConfirm 自带红色触发按钮，去掉自身胶囊描边只留按钮 */
.ov-danger {
  border: none;
  background: transparent;
  padding: 0;
}
.ov-danger :deep(button) {
  height: 30px;
  border-radius: 999px;
  font-size: 12px;
}
.html-frame {
  border: 1px solid var(--ops-border);
  border-radius: 4px;
  background: var(--ops-surface);
}
.frame-note {
  color: var(--ops-text-3);
  font-size: 12px;
}
/* markdown 阅读排版：轻量 prose（无 typography 插件，手写最小集） */
.md-reader {
  padding: 4px 6px;
  font-size: 14px;
  line-height: 1.75;
  color: var(--ops-text-1);
}
.md-reader :deep(h1),
.md-reader :deep(h2),
.md-reader :deep(h3) {
  margin: 1.2em 0 0.5em;
  font-weight: 600;
  line-height: 1.3;
}
.md-reader :deep(h1) { font-size: 1.5em; border-bottom: 1px solid var(--ops-border); padding-bottom: 0.3em; }
.md-reader :deep(h2) { font-size: 1.25em; }
.md-reader :deep(h3) { font-size: 1.1em; }
.md-reader :deep(p) { margin: 0.6em 0; }
.md-reader :deep(ul),
.md-reader :deep(ol) { margin: 0.6em 0; padding-left: 1.6em; }
.md-reader :deep(code) {
  font-family: var(--ops-font-mono);
  font-size: 0.9em;
  background: var(--ops-surface-2);
  border-radius: 4px;
  padding: 0.1em 0.35em;
}
.md-reader :deep(pre) {
  background: var(--ops-surface-2);
  border: 1px solid var(--ops-border);
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
}
.md-reader :deep(pre code) { background: transparent; padding: 0; }
.md-reader :deep(img) { max-width: 100%; border-radius: 8px; }
.md-reader :deep(blockquote) {
  margin: 0.6em 0;
  padding: 0.2em 1em;
  border-left: 3px solid var(--ops-border);
  color: var(--ops-text-2);
}
.md-reader :deep(table) { border-collapse: collapse; margin: 0.8em 0; }
.md-reader :deep(th),
.md-reader :deep(td) { border: 1px solid var(--ops-border); padding: 6px 12px; }
.md-reader :deep(a) { color: var(--primary); }
</style>
```

注意脚本内两处 import（`useI18n`）按 lint 习惯合并到顶部 import 区（上面为展示逻辑分组，执行时统一置顶）。

- [ ] **Step 4: deriveKind 纯函数 + 最小回归测试**

`modules/knowledge/api.ts` 追加（与后端 `_with_kind` 同规则的镜像）：

```ts
/** 与后端 kind 派生同规则（url > markdown > html）的客户端镜像，供视图/测试共用 */
export function deriveKind(item: Pick<KnowledgeResource, 'url' | 'markdown' | 'html'>): KnowledgeResource['kind'] {
  return item.url ? 'url' : item.markdown ? 'markdown' : item.html ? 'html' : null
}
```

KnowledgeDialog 与 KnowledgeView 里 kind 判定改用 `deriveKind(item)`。新建 `frontend/src/modules/knowledge/knowledge.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { deriveKind } from './api'

describe('deriveKind', () => {
  it('url 优先于 markdown/html', () => {
    expect(deriveKind({ url: 'https://a', markdown: '# m', html: '<p>x</p>' })).toBe('url')
  })
  it('markdown 优先于 html', () => {
    expect(deriveKind({ url: '', markdown: '# m', html: '<p>x</p>' })).toBe('markdown')
  })
  it('仅 html', () => {
    expect(deriveKind({ url: null, markdown: null, html: '<!doctype html>' })).toBe('html')
  })
  it('全空为 null', () => {
    expect(deriveKind({ url: '', markdown: '', html: '' })).toBeNull()
  })
})
```

- [ ] **Step 5: 构建 + 前端测试**

Run: `cd frontend && npm run build && npx vitest run`
Expected: 构建成功、vitest 全绿（含新 4 例）

- [ ] **Step 6: Commit**

```bash
git add frontend/src/modules/knowledge frontend/package.json frontend/package-lock.json
git commit -m "feat(knowledge): 新建/编辑弹窗 + 卡片遮罩三按钮 + Markdown 渲染（marked+DOMPurify、粘贴图压缩内嵌）"
```

---

### Task 5: 前端 — 站点抽屉/编辑弹窗 pages→knowledge

**Files:**
- Modify: `frontend/src/modules/sites/api.ts`（ResourceType、URL_SEGMENT）
- Modify: `frontend/src/modules/sites/SiteResourcesDrawer.vue`
- Modify: `frontend/src/modules/sites/ResourceEditModal.vue`

- [ ] **Step 1: api.ts 类型更名**

`ResourceType` → `'servers' | 'knowledge' | 'redis' | 'mq' | 'devices'`；`URL_SEGMENT` 键 `pages: 'pages'` → `knowledge: 'knowledge'`；`TEST_TYPE` 注释「pages 无连接测试」→「knowledge 无连接测试」。

- [ ] **Step 2: SiteResourcesDrawer.vue**

`TYPES` 数组 `{ key: 'pages', label: 'Page' }` → `{ key: 'knowledge', label: 'Knowledge' }`；`COLUMN_DEFS` 键 `pages` → `knowledge`（列保持 description/url 两列）；`isPage = activeType.value === 'pages'` → `=== 'knowledge'`（变量名顺带改 `isKnowledge`）；文件内其余 `'pages'` 字面量全量替换。

- [ ] **Step 3: ResourceEditModal.vue**

- `EditTarget.type` 联合类型 `'pages'` → `'knowledge'`
- `TYPES` 映射 `pages: 'Page'` → `knowledge: 'Knowledge'`
- `FIELD_DEFS` 键 `pages` → `knowledge`（字段定义不变）
- `CREATE_DEFAULTS` 键 `pages` → `knowledge`，值改 `{ url: '', html: '' }`（无 markdown 输入项，不预置）
- `save()` 校验分支：`target.type === 'pages'` → `=== 'knowledge'`，且条件扩为三选一（markdown 来自编辑回填的 item 副本，允许只改链接不动文档）：

```ts
  // knowledge：url / html / markdown 至少一个（markdown 仅来自编辑回填，本表单不编辑它）
  if (target.type === 'knowledge'
    && !String(form.value.url ?? '').trim()
    && !String(form.value.html ?? '').trim()
    && !String(form.value.markdown ?? '').trim()) {
    fieldError.value = t('knowledge.needOne')
    return
  }
```

- `data` 过滤器补一项 `!(k === 'markdown' && typeof v === 'string' && !v.trim())`（空 markdown 不提交，防抹掉文档）
- 模板：HTML 上传区的 `v-if="props.target?.type === 'pages'"` → `=== 'knowledge'`；该区块上方加文档提示（仅编辑 markdown 型条目时显示）：

```html
        <div v-if="props.target?.item?.markdown" class="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
          {{ $t('knowledge.drawerMdHint') }}
        </div>
```

- 文件内 `t('page.xxx')` 全部换 `t('knowledge.xxx')`（invalidHtml→mdInvalid 对应换成 `knowledge.mdInvalid`；htmlLoaded/htmlFailed/needOne/urlPh/htmlLabel/uploadBtn/uploadHint/htmlPh 按 Task 3 的 key 对照表换，无对应者删引用）

- [ ] **Step 4: 残留清点**

Run: `grep -rn "page" frontend/src --include=*.vue --include=*.ts -il`
人工过一遍：`page` 作为独立概念（PageResource/pageApi/`'pages'`/`page.*` i18n/`tabs.page`）应为 0；纯英文单词 page（如 onPage、totalPages、分页变量）保留。

Run: `grep -rn "PageConfig\|'pages'\|\"pages\"" backend/app backend/tests`
Expected: 仅剩 `migrate_legacy_pages`（迁移函数自身）与 import 兼容处的字面量。

- [ ] **Step 5: 构建 + 双端全量测试**

Run: `cd frontend && npm run build && npx vitest run`
Run: `uv run pytest backend/tests -q`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add frontend/src/modules/sites
git commit -m "refactor(sites): 资源抽屉 pages→knowledge（markdown 条目只读提示、空值不回写）"
```

---

### Task 6: 收尾 — build-stamp、全量验证、真实环境冒烟

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue`（build-stamp）

- [ ] **Step 1: 更新 build-stamp**

`MainLayout.vue` 侧栏底部 stamp 改为执行时刻 `bMMDD-HHMM`（`date +"%m%d-%H%M"` 取值，如 `b1028-1430`）。

- [ ] **Step 2: 双绿门槛**

Run: `uv run pytest backend/tests -q && cd frontend && npx vitest run`
Expected: 后端全部 PASS、前端全部 PASS

- [ ] **Step 3: 真实环境冒烟（需 .env 与后端运行）**

```bash
uv run --env-file .env python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 25088
# 前端 npm run dev 或构建产物经 nginx，浏览器验证：
```

冒烟清单：
1. 启动日志无迁移报错；旧 `pages` 数据出现在知识库卡片墙（RENAME 生效）
2. 新建 → 链接型：保存 → 卡片出现 → hover 遮罩打开（新标签）
3. 新建 → 文档型：粘贴一段带图片的 markdown（截图复制）→ 卡片变「文档」→ 打开阅读 → 图片正常显示、主题深浅色下排版正常
4. 新建 → HTML 型：粘贴完整 html → 阅读弹窗 sandbox 预览正常
5. 编辑：改文档名称保存 → 卡片更新；站点抽屉打开该文档条目 → 提示文案出现、保存后 markdown 未丢
6. 删除：倒计时确认 → 卡片消失
7. 深色主题重复 3/4

- [ ] **Step 4: Commit**

```bash
git add frontend/src/layouts/MainLayout.vue
git commit -m "chore: build-stamp 更新（knowledge 模块上线）"
```

---

## Self-Review 记录

- **Spec 覆盖**：更名映射表（Task 1/3/5 全覆盖）✓；markdown 字段+1MB（Task 1）✓；kind 三档派生（Task 1 Step 1 用例）✓；启动迁移+导入兼容（Task 2）✓；新建/编辑弹窗+站点只读（Task 4）✓；粘贴图片压缩（Task 4 compressImage）✓；marked+dompurify 净化渲染（Task 4）✓；hover 遮罩三按钮+倒计时删除（Task 4）✓；全屏图标删除（Task 4 重写后无 Maximize2 卡片入口）✓；抽屉保持+markdown 不抹（Task 5 data 过滤）✓；oplog 自动记录（复用通用 CRUD，无需任务）✓；测试门槛（Task 6）✓。视频/独立附件存储明确不做（spec 排除）。
- **占位符**：无 TBD；`common.cancel/save` 两 key 标注了核对命令而非假设存在。
- **类型一致性**：`KnowledgeResource`/`knowledgeApi`/`deriveKind` 在 Task 3 定义、Task 4/5 消费一致；后端 `migrate_legacy_pages` Task 2 定义与 `__init__.py` import 一致；i18n key 集中在 Task 3 定义、Task 4/5 消费同名单。
