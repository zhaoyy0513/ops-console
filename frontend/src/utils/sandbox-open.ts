/** 把 HTML 装进外层 sandbox 壳 Blob 并在新标签打开——与站内阅读同一隔离底线
 *  （allow-scripts 可跑、opaque origin 拿不到本域 cookie/storage）。内层用 srcdoc 而非
 *  src="blob:"：sandbox 无 allow-same-origin 时 opaque origin 取 blob: 会被浏览器拦截白屏。
 *  Blob 用完即回收（60s 足够浏览器完成打开动作）。Page 与 Knowledge 阅读共用。 */
export function openHtmlInNewTab(html: string) {
  const inner = html.replace(/&/g, '&amp;').replace(/"/g, '&quot;') // srcdoc 属性转义
  const shell = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;height:100%}</style></head><body><iframe sandbox="allow-scripts" srcdoc="${inner}" style="border:0;width:100%;height:100%"></iframe></body></html>`
  const url = URL.createObjectURL(new Blob([shell], { type: 'text/html;charset=utf-8' }))
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
