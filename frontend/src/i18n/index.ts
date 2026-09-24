import { createI18n } from 'vue-i18n'
import { computed, ref } from 'vue'

export type Locale = 'zh' | 'en'

const messages = {
  zh: {
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
