/**
 * The loop we ship, tested the way a child uses it.
 *
 * Every speech test before this one skipped the first four steps of the chain
 * and POSTed text straight to Core. Measured 2026-08-19: across a whole day of
 * "full lesson" runs, `POST /audio/transcriptions` was called **zero** times.
 * The teacher had never heard anything, and nothing said otherwise.
 *
 * This drives the real thing: Chromium plays a WAV as its microphone, the real
 * energy VAD in `voiceGate.ts` decides where the utterance starts and stops,
 * the real Whisper transcribes it, and the real `RoomDock` posts the result to
 * Core as a turn. It asserts on the NETWORK, not on internals, because the
 * network is what actually has to happen.
 *
 * Build the WAV with `tools/build_voice_gate_wav.py` — the silence padding is
 * not politeness, it is how the gate calibrates and how an utterance ends.
 */
import { chromium, LAUNCH_ARGS } from './lib.mjs'

const UI = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const wav = process.env.PUPIL_WAV
const expected = (process.env.PUPIL_SAID || '').trim().toLowerCase()
const WAIT_MS = Number(process.env.PUPIL_WAIT_MS || 90000)

const out = { pass: false, checks: {}, heard: null, posted: null, errors: [] }
if (!wav) {
  out.errors.push('PUPIL_WAV not set — build one with tools/build_voice_gate_wav.py')
  console.log(`@@RESULT@@ ${JSON.stringify(out)}`)
  process.exit(1)
}

// lib.mjs's helpers take no extra flags, and this needs the fake-file capture
// on top of the fake-device pair. Same LAUNCH_ARGS, one flag more.
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH,
  args: [
    ...LAUNCH_ARGS,
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
    `--use-file-for-fake-audio-capture=${wav}`,
  ],
})
const ctx = await browser.newContext({
  viewport: { width: 1024, height: 768 },
  permissions: ['microphone'],
})
const page = await ctx.newPage()

const asr = []
const turns = []
page.on('response', async (res) => {
  const url = res.url()
  if (url.includes('/audio/transcriptions')) {
    let body = null
    try { body = await res.json() } catch { /* non-JSON error body */ }
    asr.push({ status: res.status(), text: body?.text ?? null, language: body?.language ?? null })
  } else if (url.includes('/teacher/turn')) {
    turns.push({ status: res.status(), method: res.request().method() })
  }
})
page.on('pageerror', (e) => out.errors.push(String(e).slice(0, 200)))

try {
  await page.goto(`${UI}/classroom`, { waitUntil: 'networkidle' })
  // The audio/mic unlock gesture a real room gets from the adult's first tap.
  await page.mouse.click(80, 80)

  const deadline = Date.now() + WAIT_MS
  while (Date.now() < deadline && (asr.length === 0 || turns.length === 0)) {
    await page.waitForTimeout(500)
  }

  // What the room believes it heard, from its own store rather than pixels.
  out.heard = await page.evaluate(() => {
    const el = document.querySelector('[data-stage="heard"]')
    return el ? (el.textContent || '').trim() : null
  })

  const transcript = (asr.find((a) => a.text)?.text || '').trim().toLowerCase()
  out.posted = { asrCalls: asr.length, turnCalls: turns.length, transcript }

  out.checks['the microphone reached Whisper'] = asr.length > 0
  out.checks['Whisper returned words'] = transcript.length > 0
  out.checks['the words became a turn'] = turns.some((t) => t.status < 400)
  out.checks['the room echoed what it heard'] = Boolean(out.heard)
  out.checks['no page errors'] = out.errors.length === 0
  if (expected) {
    // Not an exact match: `base` writes "Hello, I'm Min." for "Hello. I am
    // Minh." and that is a child who was understood. Overlap of content words
    // is the honest bar for a smoke test; WER belongs in tests/room.
    const want = new Set(expected.replace(/[.,!?]/g, '').split(/\s+/).filter((w) => w.length > 2))
    const got = new Set(transcript.replace(/[.,!?]/g, '').split(/\s+/))
    const hit = [...want].filter((w) => got.has(w)).length
    out.checks['it heard roughly the right words'] = want.size > 0 && hit / want.size >= 0.5
    out.posted.wordOverlap = `${hit}/${want.size}`
  }
} catch (err) {
  out.errors.push(String(err).slice(0, 300))
} finally {
  await ctx.close()
  await browser.close()
}

out.pass = Object.values(out.checks).every(Boolean) && Object.keys(out.checks).length > 0
console.log(`@@RESULT@@ ${JSON.stringify(out)}`)
process.exit(out.pass ? 0 : 1)
