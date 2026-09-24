import { createI18n } from 'vue-i18n'
import { computed, ref } from 'vue'

export type Locale = 'zh' | 'en'

const messages = {
  zh: {
    help: {
      default: { title: '说明' },
      overview: {
        title: '说明',
        lines: [
          '本页展示当前站点的整体健康状态：各资源类型的数量与最严重诊断级别。',
          '任一资源异常都会汇总到「异常摘要」，点击卡片可跳转到对应模块。',
          '「最近操作」来自操作日志（保留最近 1000 条），记录所有修改/删除类操作。',
          '后台每 30 秒对全部启用资源做一轮轻量健康检查；也可点击「立即检查」手动触发。',
        ],
      },
      server: {
        title: '说明',
        lines: [
          '通过 SSH 只读采集 Linux 服务器的运行指标：CPU、内存、负载、网卡与磁盘。',
          'CPU/内存百分比按阈值着色：≥80% 黄色警告、≥90% 红色严重（阈值可按站点/资源覆盖）。',
          '系统负载（load1）与 CPU 核数比较：负载持续高于核数说明有任务在排队。',
          '「Top 进程」展示瞬时 CPU 占用最高的进程（top 第二帧数据，非生命周期平均）。',
          '数据为页面在场时每 3 秒轮询采集；标签切走自动暂停。',
        ],
      },
      mq: {
        title: '说明',
        lines: [
          '经 Jolokia HTTP 读取 ActiveMQ Artemis 管理数据：Broker 概览、JVM 内存、队列与地址。',
          'JVM Heap = MQ 进程的 Java 堆内存；百分比按 80%/90% 阈值着色，生产"MQ 内存占满"即此值逼近上限。',
          '「Topics / Queues」中：Address 是目的地（相当于 topic 名），Queue 是实际存放消息的队列；积压=消息数持续高于阈值（默认 5000 警告 / 20000 严重）。',
          '「无消费者」= 队列有消息但没有任何消费者，消息会一直堆积。',
          '「清空」会删除队列内全部积压消息（不可恢复，需倒计时确认并记录操作日志）。',
        ],
      },
      robot: {
        title: '说明',
        lines: [
          '按实例接入机器人 HTTP 接口，展示 robotCode、名称、状态、电量、位置、举升与货架编码。',
          '每个实例可配置字段映射与值映射（站点管理 → 资源 → Robot → 字段映射）：字段映射解决接口字段名差异，值映射把状态枚举翻译为可读文本（如 1=CREATE）。',
          '状态徽标颜色：绿=运行/在线，黄=空闲/充电，红=故障/离线；无法识别的状态显示为灰色并保留原始值。',
          '数据每 30 秒自动刷新；详情弹窗内的 Raw JSON 是接口返回的原始完整数据。',
        ],
      },
      redis: {
        title: '说明',
        lines: [
          '以 RedisDesktop 风格浏览被监控 Redis：DB 下拉显示各库 key 数量，支持忽略大小写的模糊搜索。',
          'Keys 树按":"前缀分层折叠（同层自然排序）；点击 key 在右侧查看/编辑。',
          '值映射编辑支持 Text 与 Json 双视图（Json 带语法高亮与实时格式校验）；TTL 可设置或清除。',
          '删除为危险操作：需 5 秒倒计时确认，并记录操作日志。',
        ],
      },
    },

    layout: {
      opsLog: '操作日志',
      sites: '站点管理',
      language: '语言',
    },
    common: {
      refresh: '刷新',
      cancel: '取消',
      save: '保存',
      test: 'Test',
      delete: '删除',
      confirm: '确认',
      enabled: '启用',
      name: '名称',
      actions: '操作',
    },
    tabs: {
      overview: 'Overview',
      server: 'Server',
      mq: 'ActiveMQ',
      robot: 'Robot',
      redis: 'Redis',
      database: 'Database',
    },
    server: {
      title: '服务器',
      select: '选择服务器',
      cpu: 'CPU',
      memory: '内存',
      network: '网络',
      disk: '磁盘',
      topProcesses: 'Top 进程',
      trend: 'CPU / 内存趋势（3s 轮询采样）',
      issues: '诊断问题',
      level: '级别',
      type: '类型',
      value: '当前值',
      threshold: '阈值',
      detail: '说明',
    },
    mq: {
      broker: 'Broker',
      instance: '选择 Artemis',
      brokerStatus: 'Broker',
      worstQueue: '队列最差状态',
      heap: 'JVM Heap（约 5s 采样）',
      heapTrend: 'Heap 趋势（约 5s 采样）',
      topQueues: '队列堆积 Top 10',
      queues: 'Topics / Queues',
      version: '版本',
      uptime: '运行',
      connections: '连接',
      consumers: '消费者',
      addresses: '地址',
      status: '状态',
      messages: '消息数',
      consumersCol: '消费者',
      delivering: 'Delivering',
      added: '累计新增',
      actions: '操作',
      view: '查看',
      empty: '清空',
      search: '模糊搜索队列名或 Address',
      issuesCol: '问题',
    },
    robot: {
      instance: 'Robot 实例',
      selectInstance: '选择 Robot 接入实例',
      robots: 'Robots（30s auto refresh）',
      action: 'Action',
      detail: 'Detail',
      mappingHint: '不同实例可配置字段映射（站点管理 → 资源 → Robot）',
    },
    redis: {
      instance: '实例',
      selectRedis: '选择 Redis',
      db: 'DB',
      search: '模糊搜索，忽略大小写',
      keys: 'Keys',
    },
    sites: {
      title: '站点管理',
      newName: '如：server-01',
      enabled: '启用',
      host: 'Host',
      port: 'Port',
      username: '用户名',
      password: '密码',
      baseUrl: 'Base URL',
      testBtn: 'Test',
      jolokiaHint: '平台经 Jolokia HTTP(8161) 读取管理数据',
    },
  },
  en: {
    help: {
      default: { title: 'Instructions' },
      overview: {
        title: 'Instructions',
        lines: [
          'This page shows overall site health: resource counts and the worst diagnosis level per type.',
          'Any abnormal resource is summarised in the issue list; clicking a card jumps to its module.',
          'Recent operations come from the audit log (last 1000 kept) and record every mutating action.',
          'A lightweight health check runs every 30s across all enabled resources; use "Check now" to trigger manually.',
        ],
      },
      server: {
        title: 'Instructions',
        lines: [
          'Read-only SSH collection of Linux metrics: CPU, memory, load, network and disks.',
          'CPU/memory are threshold-coloured: >=80% warning (amber), >=90% critical (red); thresholds can be overridden per site/resource.',
          'System load (load1) is compared against CPU cores: sustained load above core count means tasks are queuing.',
          'Top processes show instantaneous CPU (top frame 2, not lifetime average).',
          'Data is polled every 3s while the page is visible; polling pauses when the tab is hidden.',
        ],
      },
      mq: {
        title: 'Instructions',
        lines: [
          'Reads ActiveMQ Artemis management data over Jolokia HTTP: broker overview, JVM memory, queues and addresses.',
          'JVM Heap is the MQ process Java heap; percentage coloured at 80%/90% — production "MQ out of memory" means this value approaching the max.',
          'In Topics / Queues: an Address is the destination (topic name); a Queue actually stores messages. Backlog = message count above threshold (default 5000 warn / 20000 critical).',
          'No consumer = messages exist but nothing consumes them, so they pile up indefinitely.',
          'Purge deletes ALL backlog in the queue (irreversible; countdown confirmation and audit logged).',
        ],
      },
      robot: {
        title: 'Instructions',
        lines: [
          'Robots are ingested per HTTP endpoint instance showing code, name, status, battery, position, lift and shelf code.',
          'Each instance can configure field mapping and value mapping (Sites → Resources → Robot → Field mapping): field mapping resolves API field-name differences; value mapping translates status enums to readable text (e.g. 1=CREATE).',
          'Badge colours: green=running/online, amber=idle/charging, red=fault/offline; unrecognised states show grey with the raw value.',
          'Data auto-refreshes every 30s; Raw JSON in the detail modal is the exact API payload.',
        ],
      },
      redis: {
        title: 'Instructions',
        lines: [
          'RedisDesktop-style browsing of monitored Redis: DB dropdown shows key counts per DB, fuzzy case-insensitive search supported.',
          'The key tree folds on ":" prefixes (natural-sorted); click a key to view/edit on the right.',
          'The value editor supports Text and Json views (Json has syntax highlight + live validation); TTL can be set or cleared.',
          'Delete is destructive: 5-second countdown confirmation, and every change is audit-logged.',
        ],
      },
    },

    layout: {
      opsLog: 'Audit Log',
      sites: 'Sites',
      language: 'Language',
    },
    common: {
      refresh: 'Refresh',
      cancel: 'Cancel',
      save: 'Save',
      test: 'Test',
      delete: 'Delete',
      confirm: 'Confirm',
      enabled: 'Enabled',
      name: 'Name',
      actions: 'Actions',
    },
    tabs: {
      overview: 'Overview',
      server: 'Server',
      mq: 'ActiveMQ',
      robot: 'Robot',
      redis: 'Redis',
      database: 'Database',
    },
    server: {
      title: 'Server',
      select: 'Select server',
      cpu: 'CPU',
      memory: 'Memory',
      network: 'Network',
      disk: 'Disk',
      topProcesses: 'Top Processes',
      trend: 'CPU / Memory trend (3s polling)',
      issues: 'Diagnosis',
      level: 'Level',
      type: 'Type',
      value: 'Value',
      threshold: 'Threshold',
      detail: 'Detail',
    },
    mq: {
      broker: 'Broker',
      instance: 'Select Artemis',
      brokerStatus: 'Broker',
      worstQueue: 'Worst queue status',
      heap: 'JVM Heap (~5s sampling)',
      heapTrend: 'Heap trend (~5s sampling)',
      topQueues: 'Top 10 queue backlog',
      queues: 'Topics / Queues',
      version: 'Version',
      uptime: 'Uptime',
      connections: 'Connections',
      consumers: 'Consumers',
      addresses: 'Addresses',
      status: 'Status',
      messages: 'Messages',
      consumersCol: 'Consumers',
      delivering: 'Delivering',
      added: 'Added',
      actions: 'Actions',
      view: 'View',
      empty: 'Purge',
      search: 'Fuzzy search queue or address',
      issuesCol: 'Issues',
    },
    robot: {
      instance: 'Robot instance',
      selectInstance: 'Select robot endpoint',
      robots: 'Robots (30s auto refresh)',
      action: 'Action',
      detail: 'Detail',
      mappingHint: 'Per-instance field mapping (Sites → Resources → Robot)',
    },
    redis: {
      instance: 'Instance',
      selectRedis: 'Select Redis',
      db: 'DB',
      search: 'Fuzzy search, case-insensitive',
      keys: 'Keys',
    },
    sites: {
      title: 'Site Management',
      newName: 'e.g. server-01',
      enabled: 'Enabled',
      host: 'Host',
      port: 'Port',
      username: 'Username',
      password: 'Password',
      baseUrl: 'Base URL',
      testBtn: 'Test',
      jolokiaHint: 'Management data read via Jolokia HTTP(8161)',
    },
  },
}

const STORAGE_KEY = 'ops-locale'

export const locale = ref<Locale>((localStorage.getItem(STORAGE_KEY) as Locale) || 'zh')

export const i18n = createI18n({
  legacy: false,
  globalInjection: true, // 模板内可直接用 $t
  locale: locale.value,
  fallbackLocale: 'zh',
  messages,
})

export default i18n

export function setLocale(l: Locale) {
  locale.value = l
  i18n.global.locale.value = l
  localStorage.setItem(STORAGE_KEY, l)
}

// 语言变化时同步 naive-ui 的组件语言（App.vue watch）
export const naiveLocale = computed(() => (locale.value === 'zh' ? 'zh-CN' : 'en-US'))
export const naiveDateLocale = computed(() => (locale.value === 'zh' ? 'zh-CN' : 'dateUS'))
