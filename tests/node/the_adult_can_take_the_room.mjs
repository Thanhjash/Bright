/**
 * The adult's console, end to end.
 *
 * NORTH-STAR §1 has called the facilitator "the safety authority in the room"
 * since the first draft. Until 2026-08-20 that was a sentence with nothing
 * behind it: every button on /control sent a WebSocket frame that is not in
 * Core's CLIENT_EVENTS allowlist, so it was rejected before any handler -- and
 * there was no handler to reject it to, because the receiving side had never
 * been written. Zero of the buttons did anything.
 *
 * This drives the two that now exist, against a real Core.
 */
import { chromium, LAUNCH_ARGS } from './lib.mjs'

const UI = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const CORE = process.env.CORE_HTTP || 'http://127.0.0.1:8004'
const out = { pass: false, checks: {}, errors: [] }

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, args: LAUNCH_ARGS })
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await ctx.newPage()
page.on('pageerror', (e) => out.errors.push(String(e).slice(0, 160)))

const status = async () => (await fetch(`${CORE}/teacher/status`)).json()

try {
  await page.goto(`${UI}/control`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)

  // The buttons the lesson graph left behind are gone. A console whose
  // controls do nothing is worse than no console.
  for (const gone of ['start-lesson', 'repeat', 'back', 'skip']) {
    out.checks[`no dead "${gone}" button`] =
      (await page.locator(`[data-testid="${gone}"]`).count()) === 0
  }

  // Pause: the adult holds the lesson.
  await page.locator('[data-testid="pause"]').click()
  await page.waitForTimeout(1200)
  out.checks['pause reaches Core'] = Boolean((await status()).pausedByAdult)

  // Resume: the adult gives it back.
  await page.locator('[data-testid="resume"]').click()
  await page.waitForTimeout(1200)
  out.checks['resume reaches Core'] = !(await status()).pausedByAdult

  out.checks['no page errors'] = out.errors.length === 0
} catch (err) {
  out.errors.push(String(err).slice(0, 240))
} finally {
  await ctx.close()
  await browser.close()
}

out.pass = Object.keys(out.checks).length > 0 && Object.values(out.checks).every(Boolean)
console.log(`@@RESULT@@ ${JSON.stringify(out)}`)
process.exit(out.pass ? 0 : 1)
