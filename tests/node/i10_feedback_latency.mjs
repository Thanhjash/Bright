/**
 * I10 — interaction → visual feedback, measured. Must be under 100 ms (NS-2).
 *
 * Measured in the page's own clock, around a real Chromium input event:
 *
 *   t0     the `pointerdown` reaches the button (capture phase, before React)
 *   tAttr  the button's class actually changes to the pressed state
 *   tPaint the first animation frame after that change — the frame a child
 *          could see
 *
 * `tPaint` is the honest number. A class attribute that mutates in 2 ms and
 * paints 300 ms later is not feedback.
 *
 * The round trip to the graded reveal is measured too, as context. It is not
 * the gate: NS-2's promise is that the *press* is instant, and the reveal is
 * allowed to take a beat.
 */
import { config, coreApi, launch, newPage, result, sleep, store, waitForStore } from './lib.mjs'

const cfg = config()
const core = coreApi(cfg.coreHttp)
const out = { ok: false, samples: [] }

const browser = await launch()
try {
  const page = await newPage(browser)
  await page.goto(`${cfg.uiOrigin}/classroom`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await waitForStore(page, (s) => s.connection.state === 'open' && !s.awaitingSnapshot, {
    label: 'connected',
  })

  const rounds = cfg.rounds ?? 3
  for (let round = 0; round < rounds; round++) {
    // A fresh question each round; `repeat` re-enters the same activity so the
    // reveal is cleared and the buttons are live again.
    await core.startLesson(2) // q_meow
    await core.waitForScene('choice', 60000)
    const s = await waitForStore(
      page,
      (st) => st.scene?.kind === 'choice' && !st.scene?.props?.revealed,
      { label: 'live choice board' },
    )
    const optionId = s.scene.props.options[0].id
    await sleep(700) // let the entry animation settle so it is not what we time

    const handle = await page.evaluateHandle((id) => {
      const buttons = Array.from(document.querySelectorAll('button'))
      const btn = buttons.find((b) => (b.textContent || '').trim().includes(id)) || buttons[0]
      const probe = { t0: null, tAttr: null, tPaint: null, found: Boolean(btn) }
      window.__probe = probe
      if (!btn) return probe
      btn.addEventListener(
        'pointerdown',
        () => {
          probe.t0 = performance.now()
        },
        { capture: true, once: true },
      )
      const mo = new MutationObserver(() => {
        if (probe.tAttr === null && btn.className.includes('scale-[0.95]')) {
          probe.tAttr = performance.now()
          requestAnimationFrame(() => {
            probe.tPaint = performance.now()
          })
        }
      })
      mo.observe(btn, { attributes: true, attributeFilter: ['class'] })
      const r = btn.getBoundingClientRect()
      probe.x = r.x + r.width / 2
      probe.y = r.y + r.height / 2
      return probe
    }, optionId)

    const probe0 = await handle.jsonValue()
    if (!probe0.found) throw new Error('no option button found on the choice board')

    const clickedAt = Date.now()
    await page.mouse.click(probe0.x, probe0.y)
    await sleep(400)
    const probe = await page.evaluate(() => ({ ...window.__probe }))

    // The graded reveal, for context.
    let revealMs = null
    try {
      await waitForStore(page, (st) => Boolean(st.scene?.props?.revealed), {
        timeout: 8000,
        label: 'reveal',
      })
      revealMs = Date.now() - clickedAt
    } catch {
      /* recorded as null */
    }

    out.samples.push({
      optionId,
      attrMs: probe.t0 !== null && probe.tAttr !== null ? probe.tAttr - probe.t0 : null,
      paintMs: probe.t0 !== null && probe.tPaint !== null ? probe.tPaint - probe.t0 : null,
      revealMs,
    })
    await sleep(2500) // past the reveal hold before restarting the activity
  }

  await core.control('pause')
  out.pageErrors = page.__pageErrors
  out.ok = true
} catch (err) {
  out.error = String(err && err.stack ? err.stack : err)
} finally {
  await browser.close()
}

result(out)
