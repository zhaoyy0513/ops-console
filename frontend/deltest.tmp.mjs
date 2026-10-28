import { chromium } from 'file:///D:/workplace/node/cache/_npx/9833c18b2d85bc59/node_modules/playwright-core/index.mjs'
const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const errs = []
page.on('pageerror', e => errs.push(e.message.slice(0, 120)))
const apiCalls = []
page.on('request', r => { if (r.method() === 'DELETE') apiCalls.push(r.url()) })
await page.goto('http://127.0.0.1:25999/console/site/28c0419a/page')
await page.evaluate(() => localStorage.setItem('ops-theme', 'light'))
await page.reload({ waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
// 打开资源抽屉（TTI 站点页 → 站点管理 → 资源；直接从站点管理页开抽屉）
await page.goto('http://127.0.0.1:25999/sites')
await page.waitForTimeout(1200)
await page.locator('tbody button', { hasText: '资源' }).nth(1).click() // TTI
await page.waitForTimeout(700)
await page.locator('[role=tab]', { hasText: 'Page' }).click()
await page.waitForTimeout(700)
// 找 __temp_delete_test__ 行的删除按钮
const row = page.locator('tbody tr', { hasText: '__temp_delete_test__' })
console.log('row found:', await row.count())
const before = await page.evaluate(() => document.querySelectorAll('[role=dialog] tbody tr').length)
await row.locator('button', { hasText: '删除' }).click()
await page.waitForTimeout(700)
const confirmVisible = await page.evaluate(() => {
  const ad = [...document.querySelectorAll('[role=alertdialog]')]
  return { open: ad.length > 0, text: ad[0]?.textContent?.slice(0, 80) }
})
console.log('confirm dialog:', JSON.stringify(confirmVisible))
// 点确认删除
await page.locator('[role=alertdialog] button', { hasText: '删除' }).click()
await page.waitForTimeout(1200)
const after = await page.evaluate(() => document.querySelectorAll('[role=dialog] tbody tr').length)
console.log('rows before/after:', before, '->', after)
console.log('DELETE calls:', apiCalls)
console.log('errs:', errs.slice(0, 3))
await page.screenshot({ path: 'del.tmp.png' })
await browser.close()
