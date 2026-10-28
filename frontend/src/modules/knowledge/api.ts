import api from '../../api'

/** 知识库文档：任意格式文件（≤1MB）。元数据在列表接口返回，文件字节走 content 端点。 */
export interface KnowledgeDoc {
  id: string
  name: string
  description: string
  filename: string
  mime: string
  size: number
  created_at: string
}

export const knowledgeApi = {
  list: (siteId: string) => api.get<KnowledgeDoc[]>(`/knowledge/${siteId}`),
  /** 上传：multipart（文件字节不进 JSON，省 base64 膨胀） */
  create: (siteId: string, file: File, name: string, description = '') => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', name)
    fd.append('description', description)
    return api.post<KnowledgeDoc>(`/knowledge/${siteId}`, fd)
  },
  /** 编辑仅改名（文件内容创建后不可变） */
  update: (siteId: string, id: string, data: Record<string, unknown>) =>
    api.put<KnowledgeDoc>(`/knowledge/${siteId}/${id}`, data),
  remove: (siteId: string, id: string) => api.delete<void>(`/knowledge/${siteId}/${id}`),
  /** 文件原始字节地址（file-viewer 预览 / 浏览器直开用） */
  contentUrl: (siteId: string, id: string) => `/api/knowledge/${siteId}/${id}/content`,
}

/** 单文件上限，与后端 MAX_FILE_BYTES 对齐（前端先行拦截，给出即时提示） */
export const MAX_FILE_BYTES = 1_000_000

/** 扩展名（小写，无点）——用于图标与分类；MIME 不可靠时以扩展名为准 */
export function fileExt(doc: Pick<KnowledgeDoc, 'filename' | 'mime'>): string {
  const fromName = doc.filename?.includes('.') ? doc.filename.split('.').pop()!.toLowerCase() : ''
  return fromName || ''
}

/** 人类可读大小 */
export function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

/** 预览类型：image / pdf / video / audio / text / office / other（决定卡片图标与徽标） */
export type PreviewKind = 'image' | 'pdf' | 'video' | 'audio' | 'text' | 'office' | 'other'

const OFFICE_EXT = new Set([
  'doc', 'docx', 'xls', 'xlsx', 'csv', 'ppt', 'pptx', 'ofd', 'rtf', 'odt', 'ods', 'odp',
])
const TEXT_EXT = new Set(['txt', 'md', 'markdown', 'log', 'json', 'xml', 'yaml', 'yml', 'ini', 'conf', 'sh', 'py'])

export function previewKind(doc: Pick<KnowledgeDoc, 'filename' | 'mime'>): PreviewKind {
  const mime = doc.mime ?? ''
  const ext = fileExt(doc)
  if (mime.startsWith('image/')) return 'image'
  if (mime === 'application/pdf' || ext === 'pdf') return 'pdf'
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('audio/')) return 'audio'
  if (OFFICE_EXT.has(ext)) return 'office'
  if (mime.startsWith('text/') || TEXT_EXT.has(ext)) return 'text'
  return 'other'
}

/** 上传前校验：空文件 / 超限。返回错误文案 key，null 表示通过 */
export function validateUpload(file: File): 'knowledge.fileEmpty' | 'knowledge.fileTooLarge' | null {
  if (file.size === 0) return 'knowledge.fileEmpty'
  if (file.size > MAX_FILE_BYTES) return 'knowledge.fileTooLarge'
  return null
}
