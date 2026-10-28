import api from '../../api'

/** 知识库文档：仅 Markdown（图片以 base64 内嵌正文，单篇 1M 字符上限由后端约束）。 */
export interface KnowledgeDoc {
  id: string
  name: string
  description: string
  markdown?: string | null
  enabled?: boolean
}

export const knowledgeApi = {
  list: (siteId: string) => api.get<KnowledgeDoc[]>(`/knowledge/${siteId}`),
  create: (siteId: string, data: Record<string, unknown>) =>
    api.post<KnowledgeDoc>(`/knowledge/${siteId}`, data),
  update: (siteId: string, id: string, data: Record<string, unknown>) =>
    api.put<KnowledgeDoc>(`/knowledge/${siteId}/${id}`, data),
  remove: (siteId: string, id: string) => api.delete<void>(`/knowledge/${siteId}/${id}`),
}

/** 拖拽文件分类（同步纯函数，便于测试）：.md/.markdown/text-markdown → 正文；image/* → 内嵌图 */
export interface DropClassification {
  markdownFiles: File[]
  imageFiles: File[]
}

export function classifyDropFiles(files: File[]): DropClassification {
  const isMd = (f: File) => {
    const n = f.name.toLowerCase()
    return n.endsWith('.md') || n.endsWith('.markdown') || f.type === 'text/markdown'
  }
  return {
    markdownFiles: files.filter(isMd),
    imageFiles: files.filter((f) => f.type.startsWith('image/')),
  }
}

/** 图片 → canvas 压缩（1280px / JPEG 0.8）→ base64 data URI。
 *  先铺白底：透明 PNG 直接压 JPEG 会变黑底。视图与弹窗共用。 */
export async function compressImage(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file)
  try {
    const scale = Math.min(1, 1280 / bitmap.width)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/jpeg', 0.8)
  } finally {
    bitmap.close()
  }
}
