/**
 * I3 — reload the tab mid-activity; the lesson must resume, not restart.
 *
 * PROTOCOL §9.1: to resnapshot, a client re-sends `client.hello`, and the
 * server must answer every hello with a full `scene.snapshot`. A reload is the
 * hardest version of that: brand new page, `stateVersion` 0, nothing local.
 *
 * Three things are checked, and only the first is obvious:
 *
 *   1. after the reload the board shows the *same activity*, not activity 0
 *   2. core's own lesson position did not move — a reload must not be able to
 *      restart a class
 *   3. the page opened exactly ONE WebSocket. This project has already shipped
 *      a version that opened two (React lifecycle ↔ socket lifecycle) and froze
 *      the stage on a false seq gap; `/dev/state.clients` is the only place
 *      that shows it.
 */
import { config, coreApi, launch, newPage, result, sleep, store, waitForStore } from './lib.mjs'

const cfg = config()
const core = coreApi(cfg.coreHttp)
const out = { ok: false }

const browser = await launch()
try {
  const page = await newPage(browser)

  const before = (await core.state()).clients
  await page.goto(`${cfg.uiOrigin}/classroom`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await waitForStore(page, (s) => s.connection.state === 'open' && !s.awaitingSnapshot, {
    label: 'first connect + snapshot',
  })
  await sleep(1500)
  out.connectionsForOnePageLoad = (await core.state()).clients - before

  // Drive the lesson to a distinctive activity: the question, not the hook.
  await core.startLesson(0)
  await core.waitForScene('choice', 90000)
  const serverBefore = await core.state()
  out.indexBefore = serverBefore.runner.index
  out.sceneBefore = serverBefore.snapshot.scene.kind
  out.versionBefore = serverBefore.stateVersion

  // `scene.update` and `lesson.position` are separate frames; wait for both to
  // have landed before recording "where the UI was", or the baseline is a
  // half-applied activity and the comparison after the reload is meaningless.
  const uiBefore = await waitForStore(
    page,
    (s) => s.scene?.kind === 'choice' && s.lesson?.activityIndex === serverBefore.runner.index,
    { label: 'choice fully applied on screen' },
  )
  out.uiIndexBefore = uiBefore.lesson?.activityIndex
  out.promptBefore = uiBefore.scene?.props?.prompt ?? null

  // ── the tab is reloaded, mid-activity ────────────────────────────────
  out.clientsBeforeReload = (await core.state()).clients
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
  const uiAfter = await waitForStore(
    page,
    (s) => s.connection.state === 'open' && !s.awaitingSnapshot && s.scene !== null,
    { label: 'resnapshot after reload', timeout: 30000 },
  )
  await sleep(1200)

  const serverAfter = await core.state()
  out.indexAfter = serverAfter.runner.index
  out.sceneAfter = serverAfter.snapshot.scene.kind
  out.uiIndexAfter = uiAfter.lesson?.activityIndex
  out.uiSceneAfter = uiAfter.scene?.kind
  out.promptAfter = uiAfter.scene?.props?.prompt ?? null
  out.uiVersionAfter = uiAfter.stateVersion
  out.awaitingSnapshot = uiAfter.awaitingSnapshot
  // One tab, one socket. A reload must retire the old one, not stack a second.
  out.clientsAfterReload = (await core.state()).clients

  out.pageErrors = page.__pageErrors
  out.ok = true
} catch (err) {
  out.error = String(err && err.stack ? err.stack : err)
} finally {
  await browser.close()
}

result(out)
