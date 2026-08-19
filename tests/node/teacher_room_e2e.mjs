/**
 * The whole product, from a cold room.
 *
 * Opens /classroom and touches NOTHING else -- no button, no session POST.
 * She must open her own class, teach, and drive the board. Every assertion
 * below is about what a child in the room would actually see or hear.
 *
 * Prints one `@@RESULT@@ {json}` line, per lib.mjs.
 */
import { config, launch, result } from './lib.mjs'

const cfg = config()
const CORE = cfg.core || 'http://127.0.0.1:8004'
const BUDGET_MS = cfg.budgetMs || 900000

const HAN = /[㐀-䶿一-鿿぀-ヿ가-힯]/

const browser = await launch()
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
const consoleErrors = []
const assetGets = []
const ttsCalls = []
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 160)) })
page.on('pageerror', (e) => consoleErrors.push(String(e).slice(0, 160)))
page.on('request', (r) => {
  const u = r.url()
  if (u.includes('/assets/')) assetGets.push(u.split('/assets/')[1])
  if (u.includes('/audio/speech')) ttsCalls.push('tts')
})

await page.goto('http://127.0.0.1:3000/classroom', { waitUntil: 'domcontentloaded' })
await page.mouse.click(960, 540)          // the one permitted kiosk gesture

const scenes = []
const says = new Set()
let openedByHerself = false
let sawStartButton = false
const started = Date.now()
let lastKind = null

while (Date.now() - started < BUDGET_MS) {
  // The projector must never offer a button to begin (NS-1).
  if (await page.locator('[data-stage="start"]').count()) sawStartButton = true
  if (await page.locator('[data-stage="mic"]').count()) sawStartButton = true

  const s = await page.evaluate(() => {
    const st = globalThis.__bright?.getState?.() || {}
    return { kind: st.scene?.kind ?? null, props: st.scene?.props ?? null }
  }).catch(() => null)

  if (s?.kind && s.kind !== lastKind) {
    lastKind = s.kind
    scenes.push({ kind: s.kind, props: JSON.stringify(s.props ?? {}).slice(0, 300) })
    await page.screenshot({ path: `tests/.artifacts/e2e-${scenes.length}-${s.kind}.png` })
  }

  const status = await fetch(`${CORE}/teacher/status`).then((r) => r.json()).catch(() => null)
  if (status?.sessionOpen) openedByHerself = true
  if (status?.lastSay) says.add(status.lastSay)
  // Enough evidence once she has spoken and drawn something real.
  if (openedByHerself && says.size >= 1 && scenes.some((x) => x.kind !== 'idle')) break
  await page.waitForTimeout(3000)
}

const spoken = [...says]
const checks = {
  opened_her_own_class: openedByHerself,
  no_button_on_the_projector: !sawStartButton,
  drew_something_other_than_idle: scenes.some((s) => s.kind !== 'idle'),
  spoke_at_least_once: spoken.length > 0,
  no_unreadable_script_on_screen:
    !spoken.some((t) => HAN.test(t)) && !scenes.some((s) => HAN.test(s.props)),
  fetched_a_real_asset: assetGets.some((a) => !a.startsWith('stage/')),
  no_page_errors: consoleErrors.length === 0,
}
result({
  pass: Object.values(checks).every(Boolean),
  checks,
  scenes: scenes.map((s) => s.kind),
  spoken: spoken.map((t) => t.slice(0, 110)),
  assets: [...new Set(assetGets)].slice(0, 10),
  ttsCalls: ttsCalls.length,
  consoleErrors: [...new Set(consoleErrors)].slice(0, 5),
})
await browser.close()
