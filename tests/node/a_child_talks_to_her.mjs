/**
 * A CONVERSATION through the microphone, not one utterance.
 *
 * `hears_a_child.mjs` proves the chain works once: fake mic -> real VAD -> real
 * Whisper -> real turn. Turn TWO had never run. Everything that only breaks the
 * second time lives in that gap -- the gate re-arming after she has spoken over
 * the room, the `deaf` state on a long reply, ASR queue backpressure (it once
 * reached 200s), and whether she keeps the thread when the child's words arrive
 * as sound rather than as HTTP.
 *
 * The pupil side is one WAV with silence where she answers, because Chromium
 * takes the fake-audio file as a LAUNCH flag and rewinds it on every
 * `getUserMedia` -- one browser plays one recording, and relaunching per line
 * would drop the Stage's audio lease and close the room between sentences.
 * Build it with `tools/build_pupil_conversation.py`, which prints the span of
 * every line so this harness can wait for the right number of them.
 *
 * Asserts on the NETWORK and on the app's own store. A screenshot cannot tell
 * you she answered the child rather than the lesson.
 *
 *   PUPIL_WAV=/tmp/pupil.wav PUPIL_LINES=8 node tests/node/a_child_talks_to_her.mjs
 */
import { chromium, LAUNCH_ARGS } from './lib.mjs'

const UI = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const wav = process.env.PUPIL_WAV
const expectLines = Number(process.env.PUPIL_LINES || 8)
// The WAV itself is ~5.6 min for 8 lines; give her room past the last one.
const WAIT_MS = Number(process.env.PUPIL_WAIT_MS || 480000)

const out = { pass: false, checks: {}, heard: [], asr: [], said: [], errors: [] }
if (!wav) {
  out.errors.push('PUPIL_WAV not set — build one with tools/build_pupil_conversation.py')
  console.log(`@@RESULT@@ ${JSON.stringify(out)}`)
  process.exit(1)
}

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH,
  args: [
    ...LAUNCH_ARGS,
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
    // %noloop: the file must run out, not start the lesson over behind us.
    `--use-file-for-fake-audio-capture=${wav}%noloop`,
  ],
})
const ctx = await browser.newContext({
  viewport: { width: 1024, height: 768 },
  permissions: ['microphone'],
  // Record THIS run, not a staged one: the video and the assertions come from
  // the same browser, so the file cannot show a lesson the checks never saw.
  ...(process.env.RECORD_DIR
    ? { recordVideo: { dir: process.env.RECORD_DIR, size: { width: 1024, height: 768 } } }
    : {}),
})
const page = await ctx.newPage()

const started = Date.now()
const at = () => ((Date.now() - started) / 1000).toFixed(1)
const asr = []
const turns = []
const spoken = []

page.on('response', async (res) => {
  const url = res.url()
  if (url.includes('/audio/transcriptions')) {
    let body = null
    try { body = await res.json() } catch { /* non-JSON error body */ }
    const text = (body?.text ?? '').trim()
    asr.push({ at: at(), status: res.status(), text, language: body?.language ?? null })
    if (text) console.log(`  ${at()}s  bé ▸ ${text}`)
  } else if (url.includes('/teacher/turn')) {
    turns.push({ at: at(), status: res.status() })
  } else if (url.includes('/audio/speech')) {
    spoken.push({ at: at(), status: res.status() })
  }
})
page.on('pageerror', (e) => out.errors.push(String(e).slice(0, 200)))

// Her side comes through the app's own store subscription, the same path
// record_a_lesson.mjs uses — polling `getState` would miss a line she says and
// replaces within one tick.
page.on('console', (m) => {
  const t = m.text()
  if (!t.startsWith('@@SAY@@')) return
  const say = t.slice(7).trim()
  // The store-missing sentinel is diagnosis, not a line the class heard.
  if (!say || say === '(no store)') { out.errors.push('store subscription unavailable'); return }
  out.said.push({ at: at(), say })
  console.log(`  ${at()}s  cô ◂ ${say}`)
})

try {
  await page.goto(`${UI}/classroom`, { waitUntil: 'networkidle' })
  // The audio/mic unlock gesture a real room gets from the adult's first tap.
  await page.mouse.click(80, 80)
  await page.evaluate(() => {
    const store = window.__bright
    if (!store?.subscribe) { console.log('@@SAY@@ (no store)'); return }
    let last = ''
    store.subscribe((st) => {
      const say = st.overlaySubtitle || st.speechSubtitle || ''
      if (say && say !== last) { last = say; console.log('@@SAY@@ ' + say) }
    })
  })

  const deadline = Date.now() + WAIT_MS
  while (Date.now() < deadline && asr.filter((a) => a.text).length < expectLines) {
    await page.waitForTimeout(1000)
  }

  out.heard = asr.filter((a) => a.text).map((a) => a.text)
  out.asr = asr.map((a) => ({ at: a.at, status: a.status, language: a.language }))

  const heardCount = out.heard.length
  const answered = turns.filter((t) => t.status < 400).length

  out.checks['every pupil line reached Whisper'] = heardCount >= expectLines
  out.checks['every heard line became a turn'] = answered >= expectLines
  // The failure this test exists for: it works once and never again.
  out.checks['she answered more than once'] = out.said.length > 1
  out.checks['she answered nearly every line'] = out.said.length >= expectLines - 1
  out.checks['the room spoke out loud'] = spoken.some((s) => s.status < 400)
  out.checks['no page errors'] = out.errors.length === 0

  out.counts = {
    pupilLinesHeard: heardCount,
    turnsAccepted: answered,
    repliesSpoken: out.said.length,
    ttsCalls: spoken.length,
    asrCalls: asr.length,
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
