/**
 * TabHelp 弹窗内容（Artemis console Instructions 风格）。
 * 不经过 vue-i18n messages —— TabHelp 直接按 locale 从这里取内容，
 * 避免撑大 i18n/index.ts 主文件。zh/en 需逐条对照维护。
 */
export interface HelpSection {
  title: string
  lines: string[]
}

export type HelpLang = 'zh' | 'en'

export const helpContent: Record<HelpLang, Record<string, HelpSection>> = {
  zh: {
    default: {
      title: '说明',
      lines: ['点击页面右上角的圆形问号，可查看当前页面的详细使用说明。'],
    },

    overview: {
      title: '说明 · Overview',
      lines: [
        '本页展示当前站点的整体健康状态：顶部徽标为全站最严重级别，下方按 Server / ActiveMQ / Device / Redis 四类展示资源总数与各状态数量。',
        '资源卡片中的彩色小标签是状态计数：绿=健康、黄=警告、红=严重、灰=未知（只显示非零项）；点击整张卡片可跳转到对应模块。',
        '「异常摘要」列出所有未恢复的诊断问题：级别、资源类型、资源名、具体说明与最近检查时间。',
        '「最近操作」来自操作日志（保留最近 1000 条），记录所有修改/删除类操作；结果 SUCCESS 为绿色、失败为红色，「全部日志」可查看完整审计记录。',
        '后台每 30 秒对全部启用资源做一轮轻量健康检查，页头显示上次检查时间；也可点击「立即检查」手动触发。',
        '停用的资源不参与检查与统计；切换站点后数据自动重新加载。',
      ],
    },

    server: {
      title: '说明 · Server',
      lines: [
        '通过 SSH 只读采集 Linux 服务器的运行指标：CPU、内存、负载、网卡与磁盘；本页面没有任何写入口，不会修改服务器。',
        'CPU 卡片显示进程 + 内核态的总占用百分比，副行为核数、iowait 与 load1/5/15；系统负载持续高于 CPU 核数说明有任务在排队。',
        'CPU/内存百分比按阈值着色：<80% 绿色、≥80% 黄色警告、≥90% 红色严重（阈值可按站点/资源覆盖）。',
        '内存百分比 = 已用物理内存 / 总内存；副行为 used/total/avail 与 swap 用量。',
        '网络卡片为当前轮询周期内的收发流量 ↓/↑，errors / dropped 持续增长说明网卡异常；磁盘表列出各挂载点容量、使用率与 Inode 使用率。',
        '「Top 进程」为 CPU 占用前 5 的进程（top 第二帧瞬时数据，非生命周期平均）；命令过长自动省略，CPU% 同样按阈值着色。',
        '数据在页面在场时每 3 秒轮询采集（静默更新不转圈），浏览器标签切走自动暂停、回来恢复；趋势图每 3 秒一个采样点，刚打开需几秒积累。',
      ],
    },

    mq: {
      title: '说明 · ActiveMQ',
      lines: [
        '经 Jolokia HTTP(8161) 读取 ActiveMQ Artemis 管理数据：Broker 概览、JVM 内存、地址内存与队列明细；平台只读，不做任何写入。',
        'JVM Heap = MQ 进程的 Java 堆内存（约 5s 采样），按 80%/90% 阈值着色；生产“MQ 内存占满”即此值逼近上限，趋势图同样来自采样。',
        '地址内存是 Artemis 为消息分配的堆外内存上限 global-max-size 的占用情况，逼近上限会触发消息阻塞。',
        '「Topics / Queues」中：Address 是目的地（相当于 topic 名），Queue 是实际存放消息的队列；表格列为队列名、所属 Address、诊断状态（悬停看具体问题）、消息数、消费者与累计新增。',
        '积压判定阈值：消息数 >5000 警告（数字加粗）、>20000 严重；「无消费者」= 队列有消息但没有任何消费者，消息会一直堆积。',
        '「查看」弹出消息浏览窗，只读预览队列前 20 条消息，不会消费它们。',
        '「清空」会删除队列内全部积压消息，不可恢复：需 10 秒倒计时确认，并记录操作日志；仅在消息数 > 0 时出现。',
        '队列读取失败时每 3 秒自动重试；外部 MQ 异常不影响平台其他功能。',
      ],
    },

    knowledge: {
      title: '说明 · 知识库',
      lines: [
        '收拢站点常用入口与文档：外链卡片一键直达，Markdown / HTML 文档站内阅读。',
        '三种类型：链接（新标签打开）、Markdown 文档（支持上传 .md 或直接粘贴，粘贴图片自动压缩为 base64 内嵌）、HTML 单文件页（沙箱隔离预览）。三者按所选类型保存。',
        '卡片悬停出现遮罩：打开 / 编辑 / 删除（删除有倒计时确认）；右上「新建」自动关联当前站点。',
        'HTML 页面运行于浏览器隔离沙箱：脚本可以执行，但无法读取本平台的登录态与数据。',
        '站点管理 → 资源 → Knowledge 仍可维护链接与 HTML 页；Markdown 文档请在知识库页面编辑。',
      ],
    },

    device: {
      title: '说明 · Device',
      lines: [
        '按实例接入设备 HTTP 接口，展示设备编码、名称、状态、电量、位置、举升与货架编码；列表每 30 秒自动刷新，也可手动刷新。',
        '每个实例可配置字段映射与值映射（站点管理 → 资源 → 设备 → 字段映射）：字段映射支持绑定（直接取 JSON 字段）或模板（自由拼接文本，字段名用花括号占位）两种模式；值映射按行把原始值翻译为可读文本（如 1=CREATE），未命中显示原值。',
        '状态徽标颜色：绿=运行/在线（running/working/active/online），黄=空闲/充电/暂停（idle/charging/standby/paused），红=故障/离线（error/fault/offline/down）；无法识别的状态显示为灰色并保留原始值。',
        '电量 <20% 显示为红色，提醒及时充电。',
        '「Detail」弹窗展示设备关键信息；底部 Raw JSON 为接口返回的原始完整数据，便于核对字段映射是否正确。',
        '接口字段缺失时对应列显示“-”；不同实例（厂商）字段不一致属正常现象，通过字段映射对齐。',
      ],
    },

    redis: {
      title: '说明 · Redis',
      lines: [
        '以 RedisDesktop 风格浏览被监控 Redis：顶部 DB 下拉显示各库 key 数量，搜索框支持忽略大小写的模糊匹配。',
        'Keys 树按“:”前缀分层折叠（同层自然排序）；点击 key 在右侧查看值、类型与 TTL，key 类型用彩色徽标区分（string/hash/list/set/zset）。',
        '值编辑支持 Text 与 Json 双视图：Json 视图带语法高亮与实时格式校验，便于编辑 JSON 值。',
        'TTL 可设置或清除（清除 = 永久保留）；保存后立即生效。',
        '删除为危险操作：需 5 秒倒计时确认，并记录操作日志。',
        '本页面对目标 Redis 具备写权限（编辑/删除/TTL），请在确认实例后再操作；连接信息在「站点管理 → 资源 → Redis」中配置。',
      ],
    },
  },

  en: {
    default: {
      title: 'Instructions',
      lines: ['Click the round question mark at the top right of any page to read its detailed instructions.'],
    },

    overview: {
      title: 'Instructions · Overview',
      lines: [
        'This page shows overall site health: the top badge is the worst level site-wide, and the tiles below show total resources and status counts for Server / ActiveMQ / Device / Redis.',
        'The coloured tags in each tile are status counts: green=healthy, amber=warning, red=critical, grey=unknown (non-zero only); click a tile to jump to its module.',
        'The issue summary lists all unresolved diagnosis problems: level, resource type, resource name, detail and last check time.',
        'Recent operations come from the audit log (last 1000 kept) and record every mutating action; SUCCESS results are green, failures red — "All logs" shows the full audit trail.',
        'A lightweight health check runs every 30s across all enabled resources (last check time shown in the header); use "Check now" to trigger manually.',
        'Disabled resources are excluded from checks and stats; data reloads automatically when you switch sites.',
      ],
    },

    server: {
      title: 'Instructions · Server',
      lines: [
        'Read-only SSH collection of Linux metrics: CPU, memory, load, network and disks; this page has no write path and never modifies the server.',
        'The CPU card shows total process + kernel usage, with cores, iowait and load1/5/15 below; load sustained above the CPU core count means tasks are queuing.',
        'CPU/memory are threshold-coloured: <80% green, >=80% warning (amber), >=90% critical (red); thresholds can be overridden per site/resource.',
        'Memory % = used physical memory / total; the sub-line shows used/total/available and swap usage.',
        'The network card shows rx/tx traffic for the current poll cycle; steadily growing errors/dropped indicate a NIC problem. The disk table lists per-mount capacity, usage and inode usage.',
        'Top processes are the 5 highest by instantaneous CPU (top frame 2, not lifetime average); long commands are ellipsised and CPU% is threshold-coloured too.',
        'Data is polled every 3s while the page is visible (silent refresh, no spinner); polling pauses when the tab is hidden. Trend chart samples one point every 3s — it needs a few seconds to fill.',
      ],
    },

    mq: {
      title: 'Instructions · ActiveMQ',
      lines: [
        'Reads ActiveMQ Artemis management data over Jolokia HTTP(8161): broker overview, JVM memory, address memory and queue details; the platform is read-only.',
        'JVM Heap is the MQ process Java heap (~5s sampling), coloured at 80%/90%; production "MQ out of memory" means this value approaching the max. The trend uses the same samples.',
        'Address memory shows usage of global-max-size, the off-heap cap Artemis allocates for storing messages; approaching the cap triggers message blocking.',
        'In Topics / Queues: an Address is the destination (topic name); a Queue actually stores messages. Columns: queue name, owning address, diagnosis (hover for issues), message count, consumers and total added.',
        'Backlog thresholds: message count >5000 warning (bold), >20000 critical. "No consumer" = messages exist but nothing consumes them, so they pile up indefinitely.',
        '"View" opens a read-only browser showing the first 20 messages in the queue — it does not consume them.',
        '"Purge" deletes ALL backlog in the queue and is irreversible: 10-second countdown confirmation, audit logged; only shown when the queue has messages.',
        'Queue reads retry automatically every 3s on failure; an unreachable MQ never affects other platform features.',
      ],
    },

    knowledge: {
      title: 'Instructions · Knowledge',
      lines: [
        'Collects site entries and documents: external links one click away, Markdown / HTML docs readable in place.',
        'Three types: link (new tab), Markdown doc (upload .md or paste; pasted images are compressed and embedded as base64), single-file HTML (sandboxed preview). Only the selected type is saved.',
        'Hovering a card shows an overlay: Open / Edit / Delete (delete has a countdown confirm); "New" auto-binds the current site.',
        'HTML pages run in a browser sandbox: scripts execute but cannot read this platform’s session or data.',
        'Sites → Resources → Knowledge still manages links and HTML pages; edit Markdown docs on the Knowledge page.',
      ],
    },

    device: {
      title: 'Instructions · Device',
      lines: [
        'Devices are ingested per HTTP endpoint instance showing device code, name, status, battery and position (per-instance custom columns supported); the list auto-refreshes every 30s, or refresh manually.',
        'Each instance can configure field mapping and value mapping (Sites → Resources → Device → Field mapping): field mapping supports bind (take a JSON field directly) or template (free text with curly-brace placeholders) modes; value mapping translates raw values per line (e.g. 1=CREATE); unmatched values show as-is.',
        'Badge colours: green=running/online (running/working/active/online), amber=idle/charging/paused (idle/charging/standby/paused), red=fault/offline (error/fault/offline/down); unrecognised states show grey with the raw value.',
        'Battery <20% is shown in red as a charging reminder.',
        'The "Detail" modal shows key device info; Raw JSON at the bottom is the exact API payload, useful for verifying field mappings.',
        'Missing API fields render as "-"; field differences between instances (vendors) are expected and resolved via field mapping.',
      ],
    },

    redis: {
      title: 'Instructions · Redis',
      lines: [
        'RedisDesktop-style browsing of monitored Redis: the DB dropdown shows key counts per DB, and search is a case-insensitive fuzzy match.',
        'The key tree folds on ":" prefixes (natural-sorted); click a key to view its value, type and TTL. Key types are colour-coded badges (string/hash/list/set/zset).',
        'The value editor has Text and Json views: Json view adds syntax highlighting and live validation, handy for editing JSON values.',
        'TTL can be set or cleared (cleared = persist forever); changes take effect immediately on save.',
        'Delete is destructive: 5-second countdown confirmation, and every change is audit-logged.',
        'This page can write to the target Redis (edit/delete/TTL) — double-check the instance before operating; connections are configured under Sites → Resources → Redis.',
      ],
    },
  },
}
