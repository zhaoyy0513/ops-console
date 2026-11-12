import { ref } from 'vue'
import { contentUrl, type KnowledgeDoc } from './api'

export interface KnowledgeDownloadTask {
  id: string
  docId: string
  filename: string
  size: number
  loaded: number
  total: number
  status: 'preparing' | 'downloading' | 'done' | 'error'
  folderName?: string
  error?: string
}

/**
 * 知识库下载管理：浮动卡片 + 实时进度 + 选择本地保存文件夹。
 * 使用 File System Access API（Chromium/Edge）流式写入，避免大文件进内存。
 * 浏览器安全限制：只能拿到目录名，无法拿到完整本地路径，也无法直接打开文件夹。
 */
export function useKnowledgeDownload() {
  const tasks = ref<KnowledgeDownloadTask[]>([])

  async function startDownload(doc: KnowledgeDoc, siteId: string) {
    const id = `${doc.id}-${Date.now()}`
    const task: KnowledgeDownloadTask = {
      id,
      docId: doc.id,
      filename: doc.filename,
      size: doc.size,
      loaded: 0,
      total: doc.size,
      status: 'preparing',
    }
    tasks.value.push(task)

    const w = window as any
    try {
      if (typeof w.showDirectoryPicker !== 'function') throw new Error('NO_FILE_SYSTEM_ACCESS')

      // 必须在用户点击的同步调用链里；await 后仍保留手势（Chrome 允许）
      const dirHandle = await w.showDirectoryPicker({ mode: 'readwrite' })
      const fileHandle = await dirHandle.getFileHandle(doc.filename, { create: true })
      const writable = await fileHandle.createWritable()

      const res = await fetch(contentUrl(siteId, doc.id), { credentials: 'same-origin' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const total = Number(res.headers.get('Content-Length')) || doc.size || 0
      task.total = total
      task.status = 'downloading'

      if (!res.body) throw new Error('NO_STREAM')
      const reader = res.body.getReader()
      let loaded = 0
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        await writable.write(value)
        loaded += value.byteLength
        task.loaded = loaded
      }
      await writable.close()
      task.status = 'done'
      task.folderName = dirHandle.name
    } catch (e) {
      if ((e as Error).message === 'NO_FILE_SYSTEM_ACCESS') {
        // 兜底：走浏览器默认下载（无法显示实时进度）
        const a = document.createElement('a')
        a.href = contentUrl(siteId, doc.id)
        a.download = doc.filename
        a.click()
        task.status = 'done'
        task.folderName = '浏览器默认下载目录'
      } else {
        task.status = 'error'
        task.error = (e as Error).message
      }
    }
  }

  function removeTask(id: string) {
    tasks.value = tasks.value.filter((t) => t.id !== id)
  }

  function clearDone() {
    tasks.value = tasks.value.filter((t) => t.status !== 'done')
  }

  return { tasks, startDownload, removeTask, clearDone }
}
