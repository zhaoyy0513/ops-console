import { describe, expect, it } from 'vitest'
import { classifyDropFiles } from './api'

function mdFile(name = 'a.md') {
  return new File(['# x'], name, { type: 'text/markdown' })
}
function imgFile(name = 'b.png') {
  return new File(['x'], name, { type: 'image/png' })
}

describe('classifyDropFiles', () => {
  it('按扩展名分类 .md/.markdown', () => {
    const r = classifyDropFiles([mdFile('a.md'), mdFile('b.MARKDOWN')])
    expect(r.markdownFiles).toHaveLength(2)
    expect(r.imageFiles).toHaveLength(0)
  })
  it('按 MIME 分类图片', () => {
    const r = classifyDropFiles([imgFile('b.png'), imgFile('c.jpeg')])
    expect(r.markdownFiles).toHaveLength(0)
    expect(r.imageFiles).toHaveLength(2)
  })
  it('混合与无关文件', () => {
    const r = classifyDropFiles([mdFile(), imgFile(), new File(['x'], 'd.txt', { type: 'text/plain' })])
    expect(r.markdownFiles).toHaveLength(1)
    expect(r.imageFiles).toHaveLength(1)
  })
  it('空列表', () => {
    expect(classifyDropFiles([]).markdownFiles).toHaveLength(0)
    expect(classifyDropFiles([]).imageFiles).toHaveLength(0)
  })
})
