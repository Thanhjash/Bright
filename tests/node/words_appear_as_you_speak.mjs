/**
 * Do the words show up while the child is still talking?
 *
 * The owner's ask, exactly: "nói tới đâu, speech to text tới đó, xong 1 câu thì
 * gửi agent." Before this, one utterance meant one recording, one Whisper call
 * and one moment where everything appeared at once — up to half a minute after
 * he started speaking, with no sign in between that anything was happening.
 *
 * Now the gate cuts a fragment at every phrase break and the chip grows. This
 * asserts the two things that can silently stop being true:
 *
 *   · MORE THAN ONE transcription per utterance — the phrase stream is alive;
 *   · the chip is non-empty BEFORE the utterance ends — words really did
 *     appear while he was still speaking, which is the whole feature.
 *
 * And the thing that must never break in exchange: the sentence that reaches
 * the teacher is the WHOLE sentence, both phrases, in order.
 *
 *   PUPIL_WAV=/tmp/twophrase.mjs node tests/node/words_appear_as_you_speak.mjs
 */
import { chromium, LAUNCH_ARGS } from './lib.mjs'

const UI = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const wav = process.env.PUPIL_WAV
const must = (process.env.PUPIL_MUST_CONTAIN || '').toLowerCase().split(',').filter(Boolean)
const WAIT_MS = Number(process.env.PUPIL_WAIT_MS || 90000)

const out = { pass: false, transcriptions: 0, chipWhileSpeaking: null, finalChip: null, posted: [], errors: [] }
if (!wav) {
  out.errors.push('PUPIL_WAV not set')
  console.log(`@@RESULT@@ ${JSON.stringify(out)}`)
  process.exit(1)
}

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH,
  args: [
    ...LAUNCH_ARGS,
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
    `--use-file-for-fake-audio-capture=${wav}%noloop`,
  ],
})
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, permissions: ['microphone'] })
const page = await ctx.newPage()
page.on('pageerror', e => out.errors.push(String(e).slice(0, 200)))
page.on('response', async (res) => {
  if (res.url().includes('/audio/transcriptions')) out.transcriptions += 1
})
page.on('request', (req) => {
  if (req.url().includes('/teacher/turn') && req.method() === 'POST') {
    try { out.posted.push(JSON.parse(req.postData() || '{}').text) } catch { /* body may be gone */ }
  }
})

await page.goto(`${UI}/classroom`, { waitUntil: 'domcontentloaded' })
await page.mouse.click(640, 400)

// Watch the chip while the gate is still capturing. `data-growing="true"` is
// set for exactly as long as more phrases are expected.
const deadline = Date.now() + WAIT_MS
while (Date.now() < deadline) {
  const snap = await page.evaluate(() => {
    const chip = document.querySelector('[data-stage="heard"]')
    return chip ? { text: chip.innerText, growing: chip.getAttribute('data-growing') } : null
  }).catch(() => null)
  if (snap?.growing === 'true' && snap.text.trim() && !out.chipWhileSpeaking)
    out.chipWhileSpeaking = snap.text.trim()
  if (out.posted.length) { out.finalChip = snap?.text?.trim() ?? null; break }
  await page.waitForTimeout(250)
}

const joined = out.posted.join(' ').toLowerCase()
out.pass =
  out.transcriptions >= 2 &&
  Boolean(out.chipWhileSpeaking) &&
  out.posted.length === 1 &&
  must.every(w => joined.includes(w))
out.looking_for = must
console.log(`@@RESULT@@ ${JSON.stringify(out)}`)
await browser.close()
process.exit(out.pass ? 0 : 1)
