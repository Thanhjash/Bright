/** Stage must speak teacher say() via Piper. /learn is not the loudspeaker. */
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

const out = { ok: false, ttsUrls: [], wsTypes: [], lease: false, say: null, error: null }
const browser = await launch()
const page = await newPage(browser)
page.setDefaultTimeout(120000)

try {
  page.on('websocket', (ws) => {
    ws.on('framereceived', (frame) => {
      try {
        out.wsTypes.push(JSON.parse(String(frame.payload)).type)
      } catch {
        /* ignore */
      }
    })
  })
  page.on('request', (req) => {
    const url = req.url()
    if (url.includes('/audio/speech') || url.includes('/assets/') || url.includes('.wav'))
      out.ttsUrls.push(url)
  })
  await page.goto(`${ui}/classroom`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.mouse.click(40, 40)
  await page.waitForTimeout(800)
  const learnerId = `voice-${Date.now()}`
  const started = await fetch(`${core}/teacher/session`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      unitId: 'market-food',
      learnerId,
      learnerName: 'Minh',
      open: true,
    }),
  })
  let body = await started.json()
  out.say = body.opening?.say ?? null
  if (!out.say) {
    const turn = await fetch(`${core}/teacher/turn`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ text: 'hello' }),
    })
    body = await turn.json()
    out.say = body.say ?? null
  }
  out.say = out.say || body.clip?.transcript || null
  if (!out.say && !body.clip)
    throw new Error(`no teacher say or clip: ${JSON.stringify(body).slice(0, 240)}`)
  await page.waitForFunction(() => {
    const reqs = performance.getEntriesByType('resource').map((e) => e.name)
    return reqs.some((url) => url.includes('/audio/speech'))
  }, null, { timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(6000)
  const status = await fetch(`${core}/teacher/status`).then((r) => r.json())
  out.lease = Boolean(status.stageAudioOwner)
  await page.screenshot({ path: join(artifacts, 'classroom-voice-01.png'), fullPage: true })
  const heard = out.ttsUrls.some((url) => url.includes('/audio/speech') || url.includes('.wav'))
  if (!heard)
    throw new Error(`Stage did not play speech (${out.ttsUrls.join(', ') || 'no media requests'}; ws=${out.wsTypes.filter((t) => String(t).startsWith('speech')).join(',')})`)
  if (!out.lease) throw new Error('Stage did not become audio owner')
  out.ok = true
} catch (err) {
  out.error = String(err?.message || err)
  await page.screenshot({ path: join(artifacts, 'classroom-voice-fail.png'), fullPage: true }).catch(() => {})
} finally {
  await browser.close()
  result(out)
  if (!out.ok) process.exit(1)
}
