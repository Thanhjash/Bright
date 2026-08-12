/** V3 product composition: one persistent Chromium profile, three windows. */
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  config,
  instrumentPage,
  launchPersistent,
  resolveModuleUrl,
  result,
  sleep,
  store,
  waitForStore,
} from './lib.mjs'

const cfg = config()
const out = { ok: false }
const profile = await mkdtemp(join(tmpdir(), 'bright-v3-profile-'))
const context = await launchPersistent(profile)

try {
  await context.grantPermissions(['microphone'], { origin: cfg.uiOrigin })
  const initial = context.pages()[0]
  const stage = instrumentPage(initial)
  const control = instrumentPage(await context.newPage())

  await Promise.all([
    stage.goto(`${cfg.uiOrigin}/classroom`, { waitUntil: 'domcontentloaded', timeout: 60000 }),
    control.goto(`${cfg.uiOrigin}/control`, { waitUntil: 'domcontentloaded', timeout: 60000 }),
  ])
  await Promise.all([
    waitForStore(stage, (s) => s.connection.state === 'open' && !s.awaitingSnapshot, { label: 'Stage snapshot' }),
    waitForStore(control, (s) => s.connection.state === 'open' && !s.awaitingSnapshot, { label: 'Control snapshot' }),
  ])

  // A duplicate Stage may display, but Core leases physical audio to one page.
  const duplicate = instrumentPage(await context.newPage())
  await duplicate.goto(`${cfg.uiOrigin}/classroom`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await waitForStore(duplicate, (s) => s.connection.state === 'open' && !s.awaitingSnapshot, { label: 'duplicate Stage snapshot' })
  await sleep(800)
  const stageStates = await Promise.all([store(stage), store(duplicate)])
  out.audioLeaseOwners = stageStates.filter((s) => s.stageLease?.clientInstanceId).length
  out.stageClientIdsDifferent = stageStates[0].stageLease?.clientInstanceId !== stageStates[1].stageLease?.clientInstanceId

  // Prove that the physical Stage and mic-owning Control share ephemeral
  // answer-station cues inside this exact persistent browser composition.
  const stageActivityUrl = resolveModuleUrl(stage, /\/speech\/answerStationActivity\.ts/)
  const controlActivityUrl = resolveModuleUrl(control, /\/speech\/answerStationActivity\.ts/)
  if (!stageActivityUrl || !controlActivityUrl) throw new Error('answer-station module URL not observed')
  await stage.evaluate(async (url) => {
    const mod = await import(url)
    mod.subscribeAnswerStationActivity((activity) => { window.__answerActivity = activity })
  }, stageActivityUrl)
  await control.evaluate(async (url) => {
    const mod = await import(url)
    mod.publishAnswerStationActivity({ phase: 'listening', assignmentId: 'assignment-e2e', captureId: 'capture-e2e' })
  }, controlActivityUrl)
  await stage.waitForFunction(() => window.__answerActivity?.captureId === 'capture-e2e')
  out.broadcastActivity = await stage.evaluate(() => window.__answerActivity)

  // Product setup at the target facilitator resolution.
  const roster = control.locator('#roster-input')
  await roster.fill('learner-01, Learner 01, A1\nlearner-02, Learner 02, A2\nlearner-03, Learner 03, A3')
  await control.getByRole('button', { name: /Check microphone|Check again/ }).click()
  await control.getByRole('button', { name: 'Microphone ready' }).waitFor({ timeout: 15000 })
  await control.waitForTimeout(4200) // stage lease status + next capability report
  const start = control.getByTestId('start-lesson')
  out.startEnabled = await start.isEnabled()
  out.rosterCount = await control.locator('text=3 learners').count()
  out.overflow1366 = await control.evaluate(() => ({
    x: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    y: document.documentElement.scrollHeight > document.documentElement.clientHeight,
  }))

  const artifactDir = process.env.BRIGHT_ARTIFACTS
  await control.screenshot({ path: `${artifactDir}/v3-control-1366x768.png`, fullPage: true })
  await stage.screenshot({ path: `${artifactDir}/v3-stage-1366x768.png`, fullPage: true })
  await control.setViewportSize({ width: 1024, height: 768 })
  await control.screenshot({ path: `${artifactDir}/v3-control-1024x768.png`, fullPage: true })
  out.overflow1024 = await control.evaluate(() => ({
    x: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    y: document.documentElement.scrollHeight > document.documentElement.clientHeight,
  }))

  // The duplicate Stage was the last opened native window; put the
  // facilitator window in the foreground exactly as the operator would before
  // checking keyboard navigation.
  await control.bringToFront()
  // Persistent multi-window headless Chromium does not route the first Tab
  // from browser chrome into the document. Seed focus at the app's own skip
  // link, then use a real Tab event to validate the document focus order and
  // focus-visible treatment.
  await control.locator('a[href="#control-main"]').focus()
  await control.keyboard.press('Tab')
  out.focus = await control.evaluate(() => {
    const active = document.activeElement
    return active ? {
      tag: active.tagName,
      id: active.id,
      text: active.textContent?.trim().slice(0, 60),
      matches: active.matches(':focus-visible'),
      outlineStyle: getComputedStyle(active).outlineStyle,
      outlineWidth: getComputedStyle(active).outlineWidth,
    } : null
  })
  out.focusVisible = Boolean(out.focus && out.focus.tag !== 'BODY' && out.focus.matches && out.focus.outlineStyle !== 'none')
  out.pageErrors = [...stage.__pageErrors, ...control.__pageErrors, ...duplicate.__pageErrors]
  out.consoleErrors = [...stage.__consoleErrors, ...control.__consoleErrors, ...duplicate.__consoleErrors]
    .filter((message) => !message.includes('[speech]'))
  out.ok = true
}
catch (error) {
  out.error = String(error?.stack ?? error)
}
finally {
  await context.close()
  await rm(profile, { recursive: true, force: true })
}

result(out)
