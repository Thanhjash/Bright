/**
 * Does the microphone actually contain the word that opened the gate?
 *
 * `voiceGate` opens on energy and only then starts recording, so the sound that
 * TRIPPED the gate used to be the one sound never captured. Observed with a
 * real person on 2026-08-20: "Fine, thank you." came back from Whisper as
 * "Thank you.", every time, and the model was innocent -- the audio did not
 * contain the word. `micRecorder` now keeps a pre-roll ring and begins the clip
 * before the gate said so.
 *
 * This asserts on the ASR RESPONSE BODY, which is the only place the answer
 * lives. Two cases, and the second one matters as much as the first:
 *
 *   PUPIL_WAV=short.wav PUPIL_MUST_CONTAIN=fine   the soft onset survives
 *   PUPIL_WAV=long.wav  PUPIL_MUST_CONTAIN=english  a 7s utterance is INTACT
 *
 * The long case exists because the first version of the pre-roll fix used one
 * 3-second ring for the whole clip while the gate allows 15 seconds. Anything
 * past ~2.7s lapped it and the slice arithmetic returned a wrong length from a
 * wrong offset -- a corrupted clip, not a truncated one. A test that only ever
 * says "Fine, thank you." passes happily through that bug.
 *
 *   ./tools/build_voice_gate_wav.py --say "Fine, thank you." --voice en -o /tmp/short.wav
 *   PUPIL_WAV=/tmp/short.wav PUPIL_MUST_CONTAIN=fine node tests/node/the_first_word_survives.mjs
 */
import { chromium, LAUNCH_ARGS } from './lib.mjs'

const UI = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const wav = process.env.PUPIL_WAV
const must = (process.env.PUPIL_MUST_CONTAIN || '').trim().toLowerCase()
const WAIT_MS = Number(process.env.PUPIL_WAIT_MS || 60000)

const out = { pass: false, heard: [], durationsMs: [], errors: [] }
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
    // %noloop: Chromium repeats the file forever without it, and every repeat
    // is another clip and another Whisper call.
    `--use-file-for-fake-audio-capture=${wav}%noloop`,
  ],
})
const ctx = await browser.newContext({
  viewport: { width: 1024, height: 768 },
  permissions: ['microphone'],
})
const page = await ctx.newPage()
page.on('pageerror', e => out.errors.push(String(e).slice(0, 200)))

page.on('response', async (res) => {
  if (!res.url().includes('/audio/transcriptions')) return
  try {
    const body = await res.json()
    if (typeof body?.text === 'string') out.heard.push(body.text.trim())
  }
  catch { /* a failed transcription is reported by its absence */ }
})

await page.goto(`${UI}/classroom`, { waitUntil: 'domcontentloaded' })
// The one permitted gesture: browsers refuse an AudioContext without it.
await page.mouse.click(512, 384)

const deadline = Date.now() + WAIT_MS
while (Date.now() < deadline && out.heard.length === 0)
  await page.waitForTimeout(500)

const joined = out.heard.join(' ').toLowerCase()
out.pass = out.heard.length > 0 && (!must || joined.includes(must))
out.looking_for = must
console.log(`@@RESULT@@ ${JSON.stringify(out)}`)
await browser.close()
process.exit(out.pass ? 0 : 1)
