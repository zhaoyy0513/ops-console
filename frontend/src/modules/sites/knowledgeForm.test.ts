import { describe, expect, it } from 'vitest'
import { prepareKnowledgeData } from './knowledgeForm'

describe('prepareKnowledgeData', () => {
  it('三者全空被拒', () => {
    expect(prepareKnowledgeData({ name: 'x', url: '', markdown: '', html: '' }).error).toBe('needOne')
  })
  it('空白 markdown 不进 payload（防抹文档）', () => {
    const r = prepareKnowledgeData({ name: 'x', url: 'https://a', markdown: '   ', html: '' })
    expect(r.error).toBeUndefined()
    expect(r.data).not.toHaveProperty('markdown')
  })
  it('非空 markdown 保留（编辑回填透传）', () => {
    const r = prepareKnowledgeData({ name: 'x', url: 'https://a', markdown: '# 旧文档', html: '' })
    expect(r.data?.markdown).toBe('# 旧文档')
  })
})
