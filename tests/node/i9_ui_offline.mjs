/**
 * I9 (browser half) — the stage loses its link to core, mid-lesson.
 *
 * Two failures, and they are not the same failure:
 *
 *   CUT        the TCP connection is closed. The socket reports it. The stage
 *              should notice at once, say so in one calm line, and reconnect
 *              with a **fresh snapshot** rather than patching across the gap
 *              (PROTOCOL §1, §9.1).
 *
 *   BLACKHOLE  bytes simply stop. The socket stays open and healthy-looking;
 *              nothing is closed, nothing errors. This is the school-wifi
 *              failure, and it is the one that produces a frozen board with a
 *              confident green connection behind it.
 *
 * The lesson keeps running in core throughout, so a stage that comes back must
 * come back to where the class is, not where it left off.
 */
import { config, coreApi, launch, newPage, result, sleep, store, waitForStore } from './lib.mjs'

const cfg = config()
const core = coreApi(cfg.coreHttp)
const link = {
  cut: () => fetch(`${cfg.linkControl}/cut`).then((r) => r.json()),
  blackhole: () => fetch(`${cfg.linkControl}/blackhole`).then((r) => r.json()),
  restore: () => fetch(`${cfg.linkControl}/restore`).then((r) => r.json()),
}

const out = { ok: false, blackhole: {}, cut: {} }

const browser = await launch()
try {
  const page = await newPage(browser)

  await page.goto(`${cfg.uiOrigin}/classroom`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await waitForStore(page, (s) => s.connection.state === 'open' && !s.awaitingSnapshot, {
    label: 'connected',
  })
  await core.startLesson(0)
  await core.waitForScene('vocabulary', 60000)
  await waitForStore(page, (s) => s.scene?.kind === 'vocabulary', { label: 'vocabulary on screen' })

  // ─────────────────────────── BLACKHOLE ───────────────────────────────
  {
    await link.blackhole()
    const at = Date.now()
    const budget = cfg.blackholeWaitMs ?? 20000
    let noticed = null
    while (Date.now() - at < budget) {
      const s = await store(page)
      if (s.connection.state !== 'open') {
        noticed = Date.now() - at
        break
      }
      await sleep(250)
    }
    const s = await store(page)
    out.blackhole.noticedInMs = noticed
    out.blackhole.waitedMs = Date.now() - at
    out.blackhole.connectionState = s.connection.state
    out.blackhole.sceneWhileDead = s.scene?.kind ?? null
    // Hung or merely stale? A hung page cannot answer this at all.
    const t0 = Date.now()
    out.blackhole.stillResponsive = await page.evaluate(
      () => document.querySelectorAll('*').length > 10,
    )
    out.blackhole.evaluateMs = Date.now() - t0
    out.blackhole.noticeVisible = await page
      .getByText(/Reconnecting to the classroom|Classroom disconnected/)
      .first()
      .isVisible()
      .catch(() => false)
    await link.restore()
    await sleep(1500)
  }

  // ────────────────────────────── CUT ──────────────────────────────────
  {
    await waitForStore(page, (s) => s.connection.state === 'open', {
      timeout: 45000,
      label: 'back online before the cut',
    })
    await link.cut()
    const at = Date.now()
    const dropped = await waitForStore(page, (s) => s.connection.state !== 'open', {
      timeout: 30000,
      label: 'the stage notices a closed socket',
    })
    out.cut.noticedInMs = Date.now() - at
    out.cut.connectionState = dropped.connection.state
    const t0 = Date.now()
    out.cut.stillResponsive = await page.evaluate(
      () => document.querySelectorAll('*').length > 10,
    )
    out.cut.evaluateMs = Date.now() - t0
    out.cut.noticeVisible = await page
      .getByText(/Reconnecting to the classroom|Classroom disconnected/)
      .first()
      .isVisible()
      .catch(() => false)

    // The class carries on without the projector.
    await core.interaction('interaction.choice', { optionId: 'cat' }).catch(() => null)
    await sleep(3000)

    await link.restore()
    const restoredAt = Date.now()
    await waitForStore(
      page,
      (s) => s.connection.state === 'open' && !s.awaitingSnapshot && s.scene !== null,
      { timeout: 45000, label: 'reconnect + resnapshot' },
    )
    out.cut.recoveredInMs = Date.now() - restoredAt
  }

  await sleep(2000)
  const server = await core.state()
  const ui = await store(page)
  out.serverScene = server.snapshot.scene.kind
  out.serverVersion = server.stateVersion
  out.serverIndex = server.runner.index
  out.uiScene = ui.scene?.kind
  out.uiVersion = ui.stateVersion
  out.uiIndex = ui.lesson?.activityIndex
  out.transcript = ui.transcript.slice(-8)

  await core.control('pause')
  out.pageErrors = page.__pageErrors
  out.ok = true
} catch (err) {
  out.error = String(err && err.stack ? err.stack : err)
  try {
    await link.restore()
  } catch {
    /* best effort */
  }
} finally {
  await browser.close()
}

result(out)
