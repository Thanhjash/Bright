/**
 * What is actually on the projector right now.
 *
 * Reads the app's own store (never pixels, per lib.mjs rule 1), reports the
 * scene the teacher put up, whether the Stage owns the audio lease, and
 * whether the Live2D model loaded. Screenshots for the human.
 */
import { config, launch, result } from './lib.mjs'

const cfg = config()
const url = cfg.url || 'http://127.0.0.1:3000/classroom'
const shot = cfg.screenshot || 'tests/.artifacts/board.png'

const browser = await launch()
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
const errors = []
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)) })
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))

await page.goto(url, { waitUntil: 'domcontentloaded' })
// The kiosk needs one gesture before audio may play; the adult does this once.
await page.mouse.click(960, 540)

// Give the socket time to connect, report capabilities and take the lease.
await page.waitForFunction(() => {
  const s = globalThis.__bright?.getState?.()
  return s && s.connection?.state === 'open'
}, { timeout: 20000 }).catch(() => {})
await page.waitForTimeout(4000)

const state = await page.evaluate(() => {
  const s = globalThis.__bright?.getState?.() || {}
  return {
    connection: s.connection?.state ?? null,
    sceneKind: s.scene?.kind ?? null,
    sceneProps: s.scene?.props ?? null,
    subtitle: s.subtitle ?? s.overlay?.subtitle ?? null,
    speaking: s.avatar?.speaking ?? null,
    mouthOpen: s.avatar?.mouthOpen ?? null,
  }
})

const boardText = await page.locator('[data-stage="board"], .animate-scene-in').first()
  .innerText().catch(() => null)
const imgSrc = await page.locator('img').first().getAttribute('src').catch(() => null)

await page.screenshot({ path: shot, fullPage: false })
result({ ...state, boardText, imgSrc: imgSrc?.slice(0, 120) ?? null, errors, screenshot: shot })
await browser.close()
