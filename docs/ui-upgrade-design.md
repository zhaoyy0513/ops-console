# Ops Console 前端视觉与交互升级设计文档

> 文档版本：v1.0\
> 日期：2026-09-28\
> 前置文档：`docs/prd-tech-design-v0.2.md`（§22 UI 设计原则）\
> 范围：`frontend/` 全部 UI 层改造，不涉及后端与 API 契约\
> 状态：待评审 → 作为 UI 升级阶段的实施基准

------------------------------------------------------------------------

# 1. 背景与现状诊断

V1 功能已全部完成，但 UI 处于"能用但简陋"状态。经全量代码审查，问题清单如下：

| # | 问题 | 证据 |
|---|------|------|
| 1 | **无设计令牌系统**：颜色硬编码散落十余个文件 | `#0b63ce` 蓝在 6+ 文件重复；`pctColor()` 在 ServerView / MqView 各写一遍 |
| 2 | **naive-ui 主题零配置**：无 theme / themeOverrides / darkTheme | `App.vue` 的 NConfigProvider 只传了 locale |
| 3 | **无暗色模式**：全站写死浅色 | `style.css` 背景固定 `#f5f6f8`；CodeMirror 编辑器内联写死浅色；唯独 SSH console 写死黑色，风格割裂 |
| 4 | **零动效**：无路由过渡、无骨架屏、无数字滚动 | 全项目仅 2 处 CSS 动画（TabHelp hover、SSH blink）；`<router-view>` 裸用 |
| 5 | **指标展示原始**：大号文字 + 灰色小字 | Server 的 Network/Disk 就是 `.metric-big{font-size:34px}` 一行字；Overview 统计 tile 是裸 `<span>` |
| 6 | **表格全手写**：6+ 页面重复 thead/tbody | 无排序、无固定列、空数据是一行灰字 |
| 7 | **无品牌感**：brand 是纯文本，页面 title 还是 `frontend` | `index.html` 的 `<title>frontend</title>` |
| 8 | **字体系统缺失**：无数字等宽，轮询数字跳动错位 | 监控页数字 3 秒刷新，宽度抖动 |
| 9 | **echarts 全量引入且无主题** | `import * as echarts from 'echarts'`，颜色手动 `#0b63ce` |
| 10 | **图标库装而未用** | @vicons/ionicons5 仅 SSH 页用了 2 个图标 |

升级目标：**在遵守 PRD §22（克制、专业、无 AI 感）的前提下，让平台从"毛坯"变"精装"**。

------------------------------------------------------------------------

# 2. 升级原则（先于一切技术选型）

## 2.1 动效分级

所有动画必须归入以下三级，实现时逐个对号入座：

| 级别 | 定义 | 预算 | 示例 |
|------|------|------|------|
| **L1 必要反馈** | 状态变化的即时确认，缺失会让人怀疑"点了没？" | 时长 ≤ 250ms，必须实现 | 开关挤压回弹、按钮点击粒子、保存成功 Toast |
| **L2 氛围增强** | 提升质感但不承载信息 | 时长 ≤ 800ms，选择实现 | 数字滚动、卡片进场、路由淡入 |
| **L3 纯装饰** | 无信息量的炫技 | —— | **默认全部不采用** |

vue-bits 里大量组件属于 L3（背景粒子、玻璃拟态、发光边框），与 PRD §22 "避免大面积渐变/发光/玻璃拟态"直接冲突，**选型时逐一排除**（见 §5.3）。

## 2.2 性能守则

- 单次视图挂载最多 2 种动效（一种 L1 + 一种 L2）；
- **3s/15s 轮询刷新的数据更新不再触发进场动画**（数字滚动除外，且 tween 时长压到 ≤ 600ms）；
- 所有 canvas / WebGL 类组件（粒子、流体、Iridescence 等）一律不引入；
- 全局尊重 `prefers-reduced-motion`：通过全局 CSS 兜底关闭动画；
- 每个动画组件引入前后用 `npm run build` 对比 chunk 体积，单个组件增量 ≤ 20KB gzip。

## 2.3 不引入 Tailwind

本项目基于 naive-ui + 手写 scoped CSS，样式存量健康。vue-bits 提供 **CSS variant（非 Tailwind）版本**，jsrepo 安装时可选。**为引组件库而上 Tailwind v4 属于推倒重来，明确不做**。

------------------------------------------------------------------------

# 3. 技术底座改造（先做，动效的地基）

## 3.1 设计令牌系统

新建 `frontend/src/styles/tokens.css`，全部用 CSS 自定义属性，**单一事实来源**：

```css
:root {
  /* 品牌/主色：信息工具属性 → 蓝色系（避开 naive 默认绿，绿色留给 HEALTHY） */
  --ops-primary: #2563eb;
  --ops-primary-hover: #3b82f6;

  /* 语义状态色（与 naive-ui 语义色对齐，全站唯一定义点） */
  --ops-healthy: #18a058;
  --ops-warning: #f0a020;
  --ops-critical: #d03050;
  --ops-unknown: #909399;

  /* 中性色阶（浅色） */
  --ops-bg: #f6f7f9;
  --ops-surface: #ffffff;
  --ops-surface-2: #f2f3f5;
  --ops-border: #e5e6eb;
  --ops-text-1: #1f2329;
  --ops-text-2: #4e5969;
  --ops-text-3: #86909c;

  /* 圆角/阴影/间距（4px 栅格） */
  --ops-radius-s: 4px;
  --ops-radius-m: 8px;
  --ops-shadow-card: 0 1px 2px rgba(0, 0, 0, 0.04);
}

html.dark {
  --ops-bg: #101014;
  --ops-surface: #17171c;
  --ops-surface-2: #202026;
  --ops-border: #2e2e35;
  --ops-text-1: #e8e8ec;
  --ops-text-2: #a9a9b3;
  --ops-text-3: #6f6f79;
  /* 状态色在暗色下提亮一档 */
  --ops-warning: #f5a623;
  --ops-healthy: #27ae60;
}
```

配套动作：

- 全仓搜索删除 `#0b63ce` / `#999` / `#e5e6eb` 等硬编码，替换为 `var(--ops-*)`；
- `pctColor()` / `fmtBytes()` 收敛到 `src/utils/format.ts` 单一实现；
- naive-ui 通过 `themeOverrides` 消费同一组色值（见 §3.2）。

## 3.2 naive-ui 主题配置 + 暗色模式

**新增依赖：`@vueuse/core`**（`useDark` / `useToggle` / `useResizeObserver` / `useIntervalFn`，前端工具集事实标准，tree-shaking 后体积可忽略）。

`App.vue` 改造：

```vue
<n-config-provider
  :theme="isDark ? darkTheme : undefined"
  :theme-overrides="themeOverrides"
  :locale="locale" :date-locale="dateLocale"
>
  <n-loading-bar-provider>   <!-- 路由切换进度条，零新依赖 -->
    <n-message-provider>
      <n-dialog-provider>
        <MainLayout />
      </n-dialog-provider>
    </n-message-provider>
  </n-loading-bar-provider>
</n-config-provider>
```

- `themeOverrides`（light/dark 各一份）从 `tokens.css` 同源常量生成，覆盖 primaryColor、borderRadius、字体等；
- `useDark()` 挂 `html.dark` class 并持久化 localStorage；
- 顶栏新增主题切换按钮（太阳/月亮图标）；
- **联动改造**：ECharts 主题（§3.4）、CodeMirror 主题（one-dark / 默认亮色，替换现在的内联写死对象）、SSH console 保持深色不变。

## 3.3 字体系统（内网自托管，禁 CDN）

内网环境不能依赖 Google Fonts。采用 **fontsource npm 包**，字体随构建产物走 nginx 静态目录，离线可用：

```
npm i @fontsource-variable/inter @fontsource-variable/jetbrains-mono
```

| 用途 | 字体 | 说明 |
|------|------|------|
| 拉丁字母 + 数字 | **Inter Variable** | 现代中性无衬线，适合数据界面 |
| 代码 / 数值 / 构建戳 / SSH console | **JetBrains Mono Variable** | 等宽，替换现在的裸 monospace |
| 中文 | 系统栈：`PingFang SC` / `Microsoft YaHei` | 中文字库体积巨大，不引入 webfont |

```css
/* tokens.css */
:root {
  --ops-font-sans: 'Inter Variable', system-ui, 'PingFang SC',
                   'Microsoft YaHei', sans-serif;
  --ops-font-mono: 'JetBrains Mono Variable', ui-monospace, Consolas, monospace;
}
/* 监控数字必须等宽对齐，否则轮询刷新时宽度抖动 */
.metric-num, .n-data-table td.num {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
}
```

体积影响：Inter var latin 子集 ≈ 50KB + JBM var ≈ 40KB（woff2，gzip 后更小），一次性资源，可接受。

## 3.4 ECharts 升级

1. **按需引入**替换全量：`echarts/core` + `LineChart / PieChart / BarChart` + `TooltipComponent / GridComponent / LegendComponent / TitleComponent`，预计 chunk 体积降 50%+；
2. 注册 `ops-light` / `ops-dark` 两套主题（色板来自 tokens），`BaseChart` 随 `isDark` 切换 `setOption`；
3. `BaseChart.vue` 增强：`useResizeObserver` 替换 window resize、props 增加 `loading`（NSpin/骨架）与 `empty`（空态文案）、折线统一 `areaStyle` 渐变（opacity 0.15 → 0，属于数据可视化惯例而非装饰渐变）。

## 3.5 图标体系

@vicons/ionicons5 已安装，全面启用：

- 侧边栏菜单：每模块配一枚 outline 图标（overview=grid、server=server、redis=logo-nodeion? 用 LayersOutline、mq=swap? 用 PulseOutline、robot=hardware-chip、sites=business、ssh=terminal、audit=list）；
- MetricCard 标题图标、空态大图标、危险操作按钮图标（trash / warning）；
- 图标只用 `--ops-text-2` / 语义色两档，禁止彩色图标大杂烩（PRD §22）。

## 3.6 基础卫生

- `index.html`：`<title>` 改为 `Ops Console`；新增 SVG favicon（简单方格监视器图形）；
- brand 区加同款小 logo（12~16px SVG），保留文字；
- 手写 thead/tbody 表格分批迁移 `NDataTable`（支持排序/固定列/内置空态），迁移优先级：Server 磁盘表 → MQ 队列表 → Robot 表 → Redis 树右侧详情 → Audit（已完成）；
- 统一空态组件 `EmptyState.vue`（图标 + 文案 + 可选动作按钮），替换所有 `<td colspan style="color:#999">`。

------------------------------------------------------------------------

# 4. 新增依赖总表

| 依赖 | 类型 | 用途 | 体积代价 |
|------|------|------|----------|
| `@vueuse/core` | npm | useDark / useResizeObserver / useIntervalFn 等 | 按需 tree-shake，≈0 |
| `motion-v` | npm | Vue 官方生态动画引擎（Motion 的 Vue 版），vue-bits 的底层依赖，同时直接用于路由过渡与列表 stagger | ≈15~18KB gzip |
| `@fontsource-variable/inter` | npm | 拉丁/数字字体，自托管 | ≈50KB woff2 |
| `@fontsource-variable/jetbrains-mono` | npm | 等宽字体，自托管 | ≈40KB woff2 |
| `jsrepo`（devDependencies 或 npx） | CLI | vue-bits 组件安装器 | 0（构建时工具） |
| vue-bits 组件 × 9（见 §5） | 源码拷入 | 动效组件 | 每个数百行源码，随用随拷 |

**明确不引入**：Tailwind（§2.3）、nprogress（用 naive 自带 NLoadingBar 替代）、vue-echarts（BaseChart 封装已够用）、unplugin-auto-import（与视觉无关，不动构建链）、任何 canvas/WebGL 背景库。

------------------------------------------------------------------------

# 5. vue-bits 引入方案

## 5.1 vue-bits 是什么 / 怎么装

- React Bits（reactbits.dev）的官方 Vue 3 移植版，作者 David Haz，90+ 动效组件，MIT + Commons Clause 许可（**限制"售卖"，内部使用完全合规**）；
- 五大分类：`TextAnimations`（32）/ `Animations`（38）/ `Components`（42）/ `Micro`（32）/ `Backgrounds`；
- **不是 npm 包**，通过 jsrepo CLI 把组件源码拷贝进项目（可控、可改、无上游 break 风险）；
- 每个组件提供 Tailwind / **纯 CSS** 两种变体（我们选 CSS 变体）+ TS 变体。

安装流程：

```bash
# 一次性初始化（生成 jsrepo.json）
npx jsrepo init https://vue-bits.dev/ui

# 按需添加单个组件（交互式选择 CSS / TypeScript 变体）
npx jsrepo add https://vue-bits.dev/ui/Micro/SquishSwitch
```

> 落位约定：初始化时把 `jsrepo.json` 的分类路径全部指向
> `./src/components/bits/<分类>/`，避免组件散落在 `src/` 根目录
> （默认路径是 `./src/Micro` 这类，不符合我们的目录规范）。
> 组件源码入库，视作项目自有代码二次维护。

## 5.2 选用清单（9 个）与落位映射

### ① SquishSwitch（Micro）→ 全局开关替换 ⭐ 用户点名

挤压回弹开关，属于 L1 必要反馈。**封装一层再替换**，禁止在业务代码里裸用第三方组件（万一要换库只改封装层）：

```
src/components/OpsSwitch.vue     ← 包装 SquishSwitch，对齐 NSwitch 的
                                   v-model / disabled / size API
```

| 替换位置 | 现状 |
|----------|------|
| SitesView 站点列表行内启停 | NSwitch |
| SitesView 站点编辑表单 enabled | NSwitch |
| ResourceEditModal 资源 enabled | NSwitch |
| SshView 脚本列表行内定时启停 + 表单 isCron | NSwitch |

### ② CountUp（TextAnimations）→ 监控数字滚动

数字从旧值 tween 到新值，L2 氛围增强。轮询场景参数：`duration ≤ 600ms`（默认 2s 太慢，3 秒轮询会永远在滚）。

| 落位 |
|------|
| Overview 四个统计 tile（Server/Redis/MQ/Robot 计数） |
| Server 页 CPU% / Memory% / Network RX·TX / Disk 大数字（替换 `.metric-big` 裸 span） |
| MQ Broker KV 卡（Connections/Sessions/Consumers/Messages） |
| Redis info 条中的 Memory Used / Connected Clients / Commands/sec |

> 同类备选：Components 分类下的 `Counter`。以官方文档实际 props 为准
> （start/end/duration/easing/separator），落地时二选一。

### ③ FadeContent（Animations）→ 路由与卡片过渡

淡入过渡，L2，最克制的进场方式（不用滑入/缩放，内部工具不需要）。

| 落位 |
|------|
| `<router-view>` 外层包裹，模块切换 120ms 淡入 |
| 各模块首次挂载的内容卡片 |

### ④ SpotlightCard（Components）→ 指标卡片容器

鼠标跟随聚光效果（参数调到极弱：半径大、透明度低），L2。用于 **MetricCard**（新建的通用指标卡，见 §6.2），替换现在"n-card + 大字"的组合。声明：这是全项目唯一一处"光效"，PRD §22 允许与否以评审为准，**若认为越界则降级为普通卡片 + hover 边框高亮**。

### ⑤ ClickSpark（Animations）→ 危险操作点击反馈

点击时迸出细小粒子，L1。只用于 2 处高危按钮：

- CountdownConfirm 倒计时结束后的红色 Delete 按钮；
- SSH 脚本 Run 按钮。

（全局所有按钮都加会烦人，只给"按下去就不可逆"的操作。）

### ⑥ SpringCheck（Micro）→ 弹簧复选框

L1。落位：MQ 队列表多选（为后续批量操作预留）、Audit 日志筛选。

### ⑦ JellyRadio（Micro）→ 果冻单选

L1。落位：Redis Key 搜索的 Type 过滤（现为一组普通 tag/按钮）。

### ⑧ LatticeLoader（Micro）→ 定制加载态

L1。仅一处：SSH 脚本执行 Modal 中替换纯文本 `running...`（保留 console 黑底，加载态风格统一为细网格动画）。**不替换全站 NSpin**——表单与树加载继续用 NSpin，避免加载态两套范式。

### ⑨ StatusMark（Micro）→ 状态徽标增强（评估引入）

看名字契合 StatusBadge，**引入前先跑 demo 对比**：若其动效是"状态点呼吸/弹跳"且可配静态化，则用于 Overview 异常摘要列表行首；否则只在 StatusBadge 内手写一个 2px 呼吸点（CSS 8 行），不强求。

## 5.3 明确不采用清单（对齐 PRD §22）

| 组件/类别 | 排除原因 |
|-----------|----------|
| GlassSurface、GlassIcons、ReflectiveCard | 玻璃拟态，PRD §22 点名避免 |
| ShinyText、GradientText、StrokeText | 发光/渐变文字 |
| StarBorder、BorderGlow、ElectricBorder | 发光边框 |
| TiltedCard、PixelCard、MagicBento、ProfileCard | 3D 倾斜/像素/装饰卡片，装饰性 L3 |
| Backgrounds 全分类（Iridescence、Waves、Beams、Particles…） | Canvas/WebGL 资源占用，违背性能守则 |
| 光标类（BlobCursor、SplashCursor、Magnet 等） | 内部工具不需要光标特效 |
| SplitText、BlurText、ScrambleText 等文字动画 | 标题动画属 L3 装饰 |
| Hyperspeed、Ribbons、MetaBalls | 纯视觉秀 |
| Dock、Carousel、BounceCards、ScrollStack | 无对应业务场景 |
| Stepper、MorphSlider、ElasticSlider | 无对应业务场景 |

> 原则：**宁缺毋滥**。9 个选用组件已覆盖"反馈 + 质感"两个层次，再往上就是炫技，和 PRD "专业内部工具"定位背道而驰。

## 5.4 motion-v 直接使用的场景

vue-bits 组件之外，motion-v 本身作为动画引擎直接用于两处：

1. **列表 stagger 进场**：Overview 异常摘要、最近操作列表逐项 30ms 延迟淡入（仅首次挂载）；
2. **CountdownConfirm 升级**：倒计时数字旁加一圈 SVG 环形进度（`stroke-dashoffset` 动画），替换现在 `<span style="color:#999">` 的纯文本倒计时——这是本组件的核心升级点。

------------------------------------------------------------------------

# 6. 通用组件与页面级改造

## 6.1 通用组件改造总表

| 组件 | 动作 | 要点 |
|------|------|------|
| `StatusBadge.vue` | 增强 | 保留 n-tag，加左侧 2px 状态点（CRITICAL 时呼吸动画）；颜色改用 `--ops-*` |
| `CountdownConfirm.vue` | 重构 | 环形倒计时进度（motion-v / SVG）+ Delete 按钮包 ClickSpark + 图标；内联 style 全部迁入 scoped CSS |
| `ResourceTestButton.vue` | 增强 | 结果 tag 加成功 ✓ / 失败 ✗ 图标，失败红色 + 轻微 shake（L1，120ms）；latency 用等宽字体 |
| `MetricCard.vue` | **新建** | 图标 + 标题 + CountUp 数值 + 可选 sparkline/环形 + 顶边 2px 状态色条 + SpotlightCard 容器（可降级）。Server/MQ/Redis/Overview 四个模块复用 |
| `TrendSpark.vue` | **新建** | 迷你趋势线（echarts 按需引入后的 line，无坐标轴）；MQ 队列表堆积趋势列用 |
| `EmptyState.vue` | **新建** | 图标 + 主文案 + 副文案 + 可选动作；全站替换灰字空态 |
| `BaseChart.vue` | 增强 | 见 §3.4 |
| `CodeJsonEditor.vue` | 改造 | 主题联动暗色（one-dark），替换内联主题对象 |
| `OpsSwitch.vue` | **新建** | SquishSwitch 封装，API 对齐 NSwitch |

## 6.2 页面级改造要点

### MainLayout

- 侧边栏：菜单项加图标 + 激活态左侧 2px 主色条（高度 60% 过渡）；sider 可折叠（240px ↔ 64px，motion-v 布局动画）；
- 顶栏：Site 切换器加地球/服务器小图标；新增 **主题切换按钮**、语言切换收进同一按钮组；brand 加 logo；
- 路由：NLoadingBar 顶部进度条 + FadeContent 淡入；
- 切换站点：主内容区 150ms 淡出→淡入（掩盖数据重新加载的白屏）。

### Overview

- 统计 tile → 4 枚 MetricCard（CountUp 计数 + 状态色顶边）；
- 异常摘要 → 列表 stagger 进场，每行 StatusMark/呼吸点 + 跳转按钮；
- "最近操作"保持表格，时间列等宽字体。

### Server

- 4 指标卡全部 MetricCard 化：CPU/Mem 环形图中心数字接 CountUp；Network/Disk 告别 `.metric-big`；
- 趋势折线换主题色板 + 渐变面积；
- 磁盘表 → NDataTable，usage 列加内联进度条（n-progress，阈值变色）。

### Redis

- info 指标条 → 一行 MetricCard（小尺寸）分组展示；
- key 树加载加 NSkeleton 骨架（替换 NSpin）；
- 类型徽标 5 个手写色类 → 统一 token 色板；
- 详情编辑保存成功 → Toast（已有）+ 按钮瞬时 ✓。

### MQ

- Broker KV 卡 → MetricCard 网格；
- 队列表加 TrendSpark 堆积趋势列（数据源已有 5min 采样）；
- Purge 按钮倒计时确认复用升级后的 CountdownConfirm。

### Robot

- battery 列 → n-progress 迷你条（<20% 红），保留数字；
- 详情 Modal 的裸 `<pre>` JSON → CodeJsonEditor 只读态。

### Sites / SSH

- 全部 NSwitch → OpsSwitch（4 处）；
- 表单排版统一：label 左对齐、说明文案用 `--ops-text-3`、必填标识统一。

### Database（占位页）

- 两行文字 → 标准 EmptyState（图标 + "模块规划中" + 文案），不加任何动效（这是 demo 模块，保持极简）。

------------------------------------------------------------------------

# 7. 实施计划

严格分四期，每期结束可独立验收、可随时叫停：

### Phase A：设计底座（无任何动效）

- [ ] `tokens.css` + naive themeOverrides + 暗色模式 + 主题切换按钮
- [ ] 字体接入（Inter / JBM + tabular-nums）
- [ ] ECharts 按需引入 + 双主题 + BaseChart 增强
- [ ] `utils/format.ts` 收敛 pctColor/fmtBytes；全仓硬编码色替换
- [ ] title/favicon/brand logo；图标体系铺开
- **验收**：亮暗两套下全页面无违和，`npm run build` 通过且主 chunk 减小

### Phase B：通用组件层

- [ ] jsrepo init + 落位约定；安装 motion-v / @vueuse/core
- [ ] OpsSwitch（SquishSwitch 封装）替换 4 处 NSwitch
- [ ] StatusBadge / CountdownConfirm（环形进度）/ ResourceTestButton 增强
- [ ] MetricCard / TrendSpark / EmptyState 新建
- **验收**：vitest 既有用例全绿（CountdownConfirm 的倒计时断言需同步适配）；Storybook 式演示页人工核对

### Phase C：页面级装配

- [ ] MainLayout（菜单图标/折叠/loading bar/路由过渡）
- [ ] Overview → Server → Redis → MQ → Robot → Sites/SSH 按序改造（§6.2）
- [ ] 表格分批迁移 NDataTable
- **验收**：E2E 主路径回归（scripts/e2e_live.py 不受影响——纯前端改动）

### Phase D：动效打磨与守门

- [ ] CountUp 轮询参数调优（600ms、尊重 reduced-motion）
- [ ] ClickSpark / SpotlightCard / StatusMark 按评审结论取舍
- [ ] Lighthouse/构建体积复查；`prefers-reduced-motion` 全局兜底 CSS
- [ ] 低配机器（4G 内存笔记本 + 集显）肉眼流畅度检查
- **验收**：PRD §22 复核 + 本文档 §2.2 性能守则逐条过

------------------------------------------------------------------------

# 8. 风险与注意事项

| 风险 | 缓解 |
|------|------|
| vue-bits 上游 API 变更 | jsrepo 拷贝式引入，代码入库后与上游解耦；封装层（OpsSwitch 等）隔离业务 |
| Commons Clause 许可 | 只限"售卖库本身"，内部使用无风险；不可将组件单独打包售卖 |
| motion-v 版本兼容 | 与 vue-bits 组件声明依赖保持同版本；锁 minor |
| 动效过度 → AI 感 | §2.1 分级 + §5.3 排除清单 + 每期评审；SpotlightCard 等边界组件备好降级方案 |
| CountdownConfirm 测试断裂 | 环形进度不改变计时逻辑（setInterval 保留），vitest 断言只适配 DOM 结构 |
| i18n | 所有新增文案走 `src/i18n/index.ts` 的 zh/en 双语键，禁止硬编码中文 |
| 轮询页动效风暴 | 进场动画只在首次挂载触发；数据刷新只走 CountUp tween |

------------------------------------------------------------------------

# 9. 附录

## 9.1 命令速查

```bash
# 字体与工具
npm i @vueuse/core motion-v @fontsource-variable/inter @fontsource-variable/jetbrains-mono

# vue-bits 初始化 + 添加组件（选 CSS / TypeScript 变体）
npx jsrepo init https://vue-bits.dev/ui
npx jsrepo add https://vue-bits.dev/ui/Micro/SquishSwitch
npx jsrepo add https://vue-bits.dev/ui/TextAnimations/CountUp
npx jsrepo add https://vue-bits.dev/ui/Animations/FadeContent
npx jsrepo add https://vue-bits.dev/ui/Components/SpotlightCard
npx jsrepo add https://vue-bits.dev/ui/Animations/ClickSpark
npx jsrepo add https://vue-bits.dev/ui/Micro/SpringCheck
npx jsrepo add https://vue-bits.dev/ui/Micro/JellyRadio
npx jsrepo add https://vue-bits.dev/ui/Micro/LatticeLoader
npx jsrepo add https://vue-bits.dev/ui/Micro/StatusMark   # 评估后决定去留
```

## 9.2 vue-bits 完整分类目录（2026-09 从仓库核实）

- **Micro（32）**：BellToggle, BranchedMenu, CallChip, CodeSlots, CometDial, DodgeField, FlipCard, FolderFloat, FuseButton, GlideSelect, HoldButton, JellyRadio, LatticeLoader, PaperCrumple, PeekRating, PromptBar, PulseHeart, RefineFrame, RubberSegment, ScrubField, SlideCommit, SlingButton, SloshGauge, SpringCheck, SquishSwitch, StatusMark, SwipeRow, SwipeToast, TearTicket, ThoughtLine, VoicePill, WakeSlider
- **TextAnimations（32）**：ASCIIText, BlurText, CircularText, **CountUp**, CurvedLoop, DecryptedText, DepthText, EchoText, FallingText, FoldText, FuzzyText, GlitchText, GradientText, MaskedHeading, ParticleText, RotatingText, ScrambleText, ScrollFloat, ScrollReveal, ScrollVelocity, ShinyText, Shuffle, SplitFlapText, SplitText, StrokeText, TextCursor, TextLoop, TextPressure, TextType, TrueFocus, VariableProximity, WarpText
- **Animations（38）**：AnimatedContent, Antigravity, BlobCursor, **ClickSpark**, Crosshair, Cubes, CursorGrid, ElasticMesh, ElectricBorder, **FadeContent**, GhostCursor, GlareHover, GlowCursor, GradualBlur, HalftoneReveal, ImageTrail, LaserFlow, LogoLoop, MagicRings, Magnet, MagnetLines, MetaBalls, MetallicPaint, Noise, OrbitImages, PixelSwap, PixelTrail, PixelTransition, Ribbons, RippleDistortion, ScrollExpand, ShapeBlur, SplashCursor, StarBorder, StickerPeel, Strands, SwarmCursor, TargetCursor
- **Components（42）**：AccordionGallery, AnimatedList, BorderGlow, BounceCards, BubbleMenu, CardNav, CardSwap, Carousel, ChromaGrid, CircularGallery, Counter, CurvedInput, DecayCard, DepthCarousel, Dock, DomeGallery, DriftWall, ElasticSlider, FlowingMenu, FlyingPosters, Folder, GlassIcons, GlassSurface, GooeyNav, InfiniteMenu, InfiniteSpiral, LineSidebar, MagicBento, Masonry, ModelViewer, MorphSlider, OptionWheel, PillNav, PixelCard, ProfileCard, ReflectiveCard, ScrollStack, SpecularButton, **SpotlightCard**, Stack, StaggeredMenu, Stepper, TiltedCard
- **Backgrounds**：全部不采用

（加粗 = 本方案选用。组件名以官方站为准，安装命令里的路径大小写以 jsrepo 输出为准。）
