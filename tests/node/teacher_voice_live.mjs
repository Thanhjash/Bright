/** Careful live proof: Stage lease first, then ONE teacher session, then Piper. */
import { launch, newPage, result } from './lib.mjs'

const ui = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const core = process.env.CORE_HTTP || 'http://127.0.0.1:8004'
const out = {
  ok: false,
  lease: false,
  speechUp: false,
  wsSpeech: [],
  tts: [],
  wav: [],
  logs: [],
  pageErrors: [],
  say: null,
  clip: null,
  error: null,
}

const browser = await launch()
const page = await newPage(browser)
page.setDefaultTimeout(120000)

try {
  page.on('websocket', (ws) => {
    ws.on('framereceived', (frame) => {
      try {
        const msg = JSON.parse(String(frame.payload))
        if (String(msg.type || '').startsWith('speech.'))
          out.wsSpeech.push(msg.type)
      } catch { /* ignore */ }
    })
  })
  page.on('console', (msg) => {
    const text = msg.text()
    if (text.includes('[speech]') || text.includes('[fetch]') || msg.type() === 'error')
      out.logs.push(`${msg.type()}: ${text}`.slice(0, 240))
  })
  page.on('pageerror', (err) => out.pageErrors.push(String(err).slice(0, 240)))
  page.on('requestfailed', (req) => {
    out.logs.push(`fail ${req.url().slice(0, 160)}`)
  })
  page.on('request', (req) => {
    const url = req.url()
    if (url.includes('/audio/speech')) out.tts.push(url)
    if (url.includes('.wav')) out.wav.push(url)
  })

  await page.goto(`${ui}/classroom`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.mouse.click(80, 80)
  const leased = await page.waitForFunction(async () => {
    try {
      const body = await fetch('http://127.0.0.1:8004/teacher/status').then((r) => r.json())
      return Boolean(body.stageAudioOwner && body.speechUp)
    } catch {
      return false
    }
  }, null, { timeout: 15000 }).then(() => true).catch(() => false)
  const status = await fetch(`${core}/teacher/status`).then((r) => r.json())
  out.lease = Boolean(status.stageAudioOwner)
  out.speechUp = Boolean(status.speechUp)
  if (!leased) throw new Error(`no stage lease/speech before session: ${JSON.stringify(status)}`)

  const learnerId = `voice-live-${Date.now()}`
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
  const body = await started.json()
  out.say = body.opening?.say ?? null
  out.clip = body.opening?.clip?.asset ?? null
  await page.waitForTimeout(4000)
  const heard = out.tts.length > 0 || out.wav.length > 0
  const events = out.wsSpeech.includes('speech.turn.started')
  if (!events) throw new Error(`no speech.turn on Stage WS (${out.wsSpeech.join(',') || 'none'})`)
  if (!heard) throw new Error(`Stage got ${out.wsSpeech.join(',')} but did not fetch Piper/wav`)
  out.ok = true
} catch (err) {
  out.error = String(err?.message || err)
} finally {
  await browser.close().catch(() => {})
  result(out)
  if (!out.ok) process.exit(1)
}
