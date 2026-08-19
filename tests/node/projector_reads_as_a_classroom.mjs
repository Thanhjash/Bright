/**
 * What thirty Grade-3 children in a Hà Giang classroom actually see.
 *
 * This is a PROJECTOR, not a monitor: a cheap 1024x768 throw onto a wall, read
 * from the back of a room, by children whose second language is Vietnamese and
 * whose third is English. Two things follow, and both were violated on
 * 2026-08-19 until this file existed:
 *
 *   · no engineering text on the wall -- "protocol v3 vs vundefined", a JSON
 *     dump of a scene, a stack trace. Nobody in that room can act on it: the
 *     children read neither language, and the adult set the appliance up and
 *     walked away. Faults belong on /teacher/status, in the adult's language.
 *   · nothing may scroll sideways or bleed off the edge. There is no mouse in
 *     the room and no child may touch one, so anything off-screen is gone.
 */
import { chromium, LAUNCH_ARGS } from './lib.mjs'

const UI = process.env.UI_HTTP || 'http://127.0.0.1:3000'
const VIEWPORTS = [
  ['projector', { width: 1024, height: 768 }],
  ['wide', { width: 1366, height: 768 }],
]

// Words that mean nothing to a child and nothing to the adult in the room.
const ENGINEERING = [
  'protocol v', 'stateVersion', 'undefined', 'null', 'stack', 'Traceback',
  'TypeError', 'Exception', '{"', 'JSON', 'HTTP 4', 'HTTP 5',
]

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, args: LAUNCH_ARGS })
const checks = {}
const detail = {}

for (const [name, viewport] of VIEWPORTS) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const pageErrors = []
  page.on('pageerror', e => pageErrors.push(String(e)))
  await page.goto(`${UI}/classroom`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(2000)

  // Force the worst case the room can reach: a scene this build cannot render.
  await page.evaluate(() => {
    const store = window.__bright
    store?.getState?.().applyScene?.({ v: 999, stateVersion: 1, kind: 'text', props: { text: 'x' } })
  })
  await page.waitForTimeout(800)

  const seen = await page.evaluate(() => {
    const de = document.documentElement
    const visible = []
    for (const el of document.querySelectorAll('body *')) {
      if (el.children.length) continue
      const cs = getComputedStyle(el)
      if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue
      const box = el.getBoundingClientRect()
      if (box.width < 2 || box.height < 2) continue
      const t = (el.textContent || '').trim()
      if (t) visible.push(t)
    }
    return {
      text: visible.join(' │ '),
      horizontalScroll: de.scrollWidth > de.clientWidth + 2,
      overflowing: [...document.querySelectorAll('body *')]
        .filter(e => { const b = e.getBoundingClientRect(); return b.width > 0 && b.right > window.innerWidth + 2 })
        .length,
    }
  })

  const jargon = ENGINEERING.filter(w => seen.text.includes(w))
  checks[`${name}: no engineering text on the wall`] = jargon.length === 0
  checks[`${name}: nothing scrolls sideways`] = !seen.horizontalScroll
  checks[`${name}: nothing bleeds off the edge`] = seen.overflowing === 0
  checks[`${name}: no page errors`] = pageErrors.length === 0
  detail[name] = { jargon, overflowing: seen.overflowing, pageErrors: pageErrors.slice(0, 3) }
  await ctx.close()
}

await browser.close()
const pass = Object.values(checks).every(Boolean)
console.log(`@@RESULT@@ ${JSON.stringify({ pass, checks, detail })}`)
process.exit(pass ? 0 : 1)
