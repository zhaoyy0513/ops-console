import { describe, expect, it } from 'vitest'
import { deriveKind } from './api'

describe('deriveKind', () => {
  it('url 优先于 markdown/html', () => {
    expect(deriveKind({ url: 'https://a', markdown: '# m', html: '<p>x</p>' })).toBe('url')
  })
  it('markdown 优先于 html', () => {
    expect(deriveKind({ url: '', markdown: '# m', html: '<p>x</p>' })).toBe('markdown')
  })
  it('仅 html', () => {
    expect(deriveKind({ url: null, markdown: null, html: '<!doctype html>' })).toBe('html')
  })
  it('全空为 null', () => {
    expect(deriveKind({ url: '', markdown: '', html: '' })).toBeNull()
  })
})
