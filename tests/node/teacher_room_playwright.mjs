/** Chromium: /classroom is the room — Start class, then hold-to-talk. */
import { mkdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { launch, newPage, result } from './lib.mjs'

const ui = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const core = process.env.CORE_HTTP || 'http://127.0.0.1:8004'
const artifacts = process.env.LEARN_ARTIFACTS || join(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  '.artifacts',
)
await mkdir(artifacts, { recursive: true })

const out = {
  ok: false,
  startVisible: false,
  startLabel: null,
  woke: false,
  micVisible: false,
  phase: null,
  lease: false,
  hermesUp: false,
  speechUp: false,
  shots: [],
  error: null,
}

const browser = await launch()
const page = await newPage(browser)
page.setDefaultTimeout(120000)

try {
  await page.goto(`${ui}/classroom`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.mouse.click(80, 80)
  const start = page.locator('[data-stage="start"]')
  await start.waitFor({ state: 'visible', timeout: 15000 })
  out.startVisible = true
  out.startLabel = (await start.innerText()).replace(/\s+/g, ' ').trim()
  const shot1 = join(artifacts, 'room-asleep.png')
  await page.screenshot({ path: shot1, fullPage: true })
  out.shots.push(shot1)

  await page.waitForFunction(async () => {
    try {
      const body = await fetch('http://127.0.0.1:8004/teacher/status').then((r) => r.json())
      return Boolean(body.stageAudioOwner)
    } catch {
      return false
    }
  }, null, { timeout: 20000 }).catch(() => false)

  const status = await fetch(`${core}/teacher/status`).then((r) => r.json())
  out.lease = Boolean(status.stageAudioOwner)
  out.hermesUp = Boolean(status.hermesUp)
  out.speechUp = Boolean(status.speechUp)
  out.phase = status.phase

  if (!status.hermesUp) throw new Error(`Hermes not up: ${JSON.stringify(status)}`)
  await start.click()
  await page.locator('[data-stage="start"]').filter({ hasText: 'Waking' }).waitFor({
    state: 'visible',
    timeout: 8000,
  }).catch(() => {})
  const mic = page.locator('[data-stage="mic"]')
  await mic.waitFor({ state: 'visible', timeout: 20000 })
  out.micVisible = true
  out.woke = true
  const after = await fetch(`${core}/teacher/status`).then((r) => r.json())
  out.phase = after.phase
  const shot2 = join(artifacts, 'room-awake.png')
  await page.screenshot({ path: shot2, fullPage: true })
  out.shots.push(shot2)
  out.ok = out.startVisible && out.woke && out.micVisible
} catch (err) {
  out.error = String(err)
  try {
    const fail = join(artifacts, 'room-fail.png')
    await page.screenshot({ path: fail, fullPage: true })
    out.shots.push(fail)
  } catch { /* page may already be gone */ }
} finally {
  await browser.close().catch(() => {})
}

result(out)
if (!out.ok) process.exit(1)
