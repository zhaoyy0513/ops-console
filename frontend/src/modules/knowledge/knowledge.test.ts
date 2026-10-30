import { describe, expect, it } from 'vitest'
import { fileExt, humanSize, previewKind, validateUpload } from './api'

const doc = (filename: string, mime = '') => ({ filename, mime })

describe('previewKind', () => {
  it('按 MIME 识别图片/音视频', () => {
    expect(previewKind(doc('a.png', 'image/png'))).toBe('image')
    expect(previewKind(doc('a.mp4', 'video/mp4'))).toBe('video')
    expect(previewKind(doc('a.mp3', 'audio/mpeg'))).toBe('audio')
  })
  it('pdf 与 office 按扩展名兜底（MIME 常为 octet-stream）', () => {
    expect(previewKind(doc('手册.pdf', 'application/octet-stream'))).toBe('pdf')
    expect(previewKind(doc('报表.xlsx', ''))).toBe('office')
    expect(previewKind(doc('方案.docx', ''))).toBe('office')
  })
  it('文本与未知', () => {
    expect(previewKind(doc('run.log', ''))).toBe('text')
    expect(previewKind(doc('a.bin', 'application/octet-stream'))).toBe('other')
  })
})

describe('fileExt', () => {
  it('取小写扩展名，无扩展名为空串', () => {
    expect(fileExt(doc('A.PDF'))).toBe('pdf')
    expect(fileExt(doc('noext'))).toBe('')
  })
})

describe('humanSize', () => {
  it('B / KB / MB 三档', () => {
    expect(humanSize(512)).toBe('512 B')
    expect(humanSize(2048)).toBe('2.0 KB')
    expect(humanSize(1_500_000)).toBe('1.43 MB')
  })
})

describe('validateUpload', () => {
  it('空文件与超限分别给出对应 key，边界 200MB 放行', () => {
    expect(validateUpload(new File([], 'e.txt'))).toBe('knowledge.fileEmpty')
    const MB = 1024 * 1024
    expect(validateUpload(new File([new Uint8Array(200 * MB + 1)], 'b.bin'))).toBe('knowledge.fileTooLarge')
    expect(validateUpload(new File([new Uint8Array(200 * MB)], 'ok.bin'))).toBeNull()
  })
})
