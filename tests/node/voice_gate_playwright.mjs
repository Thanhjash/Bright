/**
 * `apps/classroom-ui/src/speech/voiceGate.ts` proved against SYNTHETIC audio.
 *
 * This is not a claim about a real classroom: clean, single-speaker TTS with
 * no overlapping voices, no reverb, no background chatter cannot separate a
 * good VAD from a mediocre one. It CAN prove the two things that are cheap to
 * get wrong and expensive to ship wrong:
 *
 *   1. Energy VAD + endpointing actually fires once, close to the speech
 *      span, on a clip shaped like `micRecorder.stop()` already returns.
 *   2. Half-duplex holds: while `avatar.speaking` is true, the gate never
 *      opens — not even against audio that is obviously, loudly speech —
 *      and it recovers to normal listening afterward.
 *
 * The WAV fed to Chromium's fake capture device is built from Piper's own
 * output (`/audio/speech`) with real silence padding, via
 * `tools/build_voice_gate_wav.py` — see that script for the exact layout.
 */
import { chromium, LAUNCH_ARGS, newPage, result } from './lib.mjs'

const ui = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const wavPath = process.env.VOICE_GATE_WAV
const speechMs = Number(process.env.VOICE_GATE_SPEECH_MS || '0')
const preMs = Number(process.env.VOICE_GATE_PRE_MS || '0')

const out = {
  ok: false,
  speechMs,
  preMs,
  phase1: null,
  phase2: null,
  errors: [],
  error: null,
}

if (!wavPath) {
  out.error = 'VOICE_GATE_WAV env var not set — see tools/build_voice_gate_wav.py'
  result(out)
  process.exit(1)
}

// Not using lib.mjs's launch()/launchPersistent() — neither takes extra
// Chromium flags, and this scenario needs `--use-file-for-fake-audio-capture`
// on top of the fake-device pair. Built from the same LAUNCH_ARGS instead of
// editing shared infra other scenarios depend on.
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH,
  args: [
    ...LAUNCH_ARGS,
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
    `--use-file-for-fake-audio-capture=${wavPath}`,
  ],
})
const page = await newPage(browser)
page.setDefaultTimeout(120000)

try {
  page.on('pageerror', (err) => out.errors.push(`pageerror: ${String(err).slice(0, 200)}`))

  await page.goto(`${ui}/classroom`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.mouse.click(80, 80) // the one permitted gesture: autoplay/mic unlock at kiosk boot
  await page.waitForFunction(() => Boolean(window.__bright), null, { timeout: 15000 })

  const outcome = await page.evaluate(async () => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
    const useClassroom = window.__bright
    const setSpeaking = (v) => {
      useClassroom.setState((s) => ({
        avatar: { ...s.avatar, speaking: v, mouthOpen: v ? s.avatar.mouthOpen : 0 },
      }))
    }

    const micMod = await import('/src/speech/micRecorder.ts')
    const gateMod = await import('/src/speech/voiceGate.ts')

    const errors = []
    const phase1 = { clips: 0, sawCapturing: false, states: [] }
    const phase2 = { clip: null, states: [], startedAt: 0 }

    // ---- Phase 1: gated for the whole pass. The WAV has unmistakable
    // speech energy in it; a correct gate must still produce ZERO clips and
    // must never even reach 'capturing', because avatar.speaking is true
    // before the gate's very first tick.
    setSpeaking(false)
    const mic1 = micMod.createMicRecorder((f) => errors.push(`mic1 device: ${f}`))
    const gate1 = gateMod.createVoiceGate(mic1, {
      onClip: () => { phase1.clips += 1 },
      onStateChange: (s) => {
        phase1.states.push(s)
        if (s === 'capturing') phase1.sawCapturing = true
      },
      onError: (msg, failure) => errors.push(`gate1: ${msg} (${failure ?? ''})`),
    })
    gate1.start()
    // Pinned, not set-once: this page is the real /classroom app with its
    // real WS bus still attached, and a live session in the background can
    // legitimately flip avatar.speaking itself mid-window. A single
    // setSpeaking(true) here was observed to lose that race — pin it at
    // twice the gate's own poll rate so every tick sees "speaking".
    const pin1 = setInterval(() => setSpeaking(true), 20)
    await sleep(6500) // pre + speech + a slice of trailing silence, all gated
    clearInterval(pin1)
    gate1.stop()
    setSpeaking(false)
    mic1.release() // force a fresh getUserMedia for phase 2 (fake file restarts at 0)
    await sleep(300)

    // ---- Phase 2: ungated throughout. Must fire exactly one accepted clip
    // shaped like micRecorder.stop()'s Clip, close to the speech span.
    const mic2 = micMod.createMicRecorder((f) => errors.push(`mic2 device: ${f}`))
    const gate2 = gateMod.createVoiceGate(mic2, {
      onClip: (clip) => {
        if (phase2.clip) return // only the first matters for this assertion
        phase2.clip = {
          durationMs: clip.durationMs,
          bytes: clip.audio.size,
          atMs: Math.round(performance.now() - phase2.startedAt),
        }
      },
      onStateChange: (s) => phase2.states.push(s),
      onError: (msg, failure) => errors.push(`gate2: ${msg} (${failure ?? ''})`),
    })
    phase2.startedAt = performance.now()
    gate2.start()
    // Same reasoning as pin1, inverted: hold the room "not speaking" so a
    // live background session's own speech turns cannot gate this phase.
    const pin2 = setInterval(() => setSpeaking(false), 20)
    await sleep(8000) // pre + speech + silence-close + margin
    clearInterval(pin2)
    gate2.stop()
    mic2.release()

    return { phase1, phase2, errors }
  })

  out.phase1 = outcome.phase1
  out.phase2 = outcome.phase2
  out.errors.push(...outcome.errors)

  const p1 = outcome.phase1
  const p2 = outcome.phase2

  if (p1.clips !== 0) throw new Error(`phase1 (gated): expected 0 clips, got ${p1.clips}`)
  if (p1.sawCapturing) throw new Error('phase1 (gated): gate reached "capturing" while avatar.speaking was true')
  if (!p1.states.includes('gated')) throw new Error(`phase1: never observed "gated" state (states=${p1.states.join(',')})`)

  if (!p2.clip) throw new Error(`phase2 (ungated): no clip fired (states=${p2.states.join(',')})`)
  if (p2.clip.durationMs < 600) throw new Error(`phase2 clip too short: ${p2.clip.durationMs}ms (< MIN_CLIP_MS)`)
  if (p2.clip.bytes <= 0) throw new Error('phase2 clip carried no audio bytes')
  if (speechMs > 0) {
    // Generous window: onset can lag up to POLL_MS, and the clip legitimately
    // includes up to SILENCE_MS of trailing silence before it closes.
    const low = speechMs * 0.5
    const high = speechMs + 1500
    if (p2.clip.durationMs < low || p2.clip.durationMs > high) {
      throw new Error(`phase2 clip duration ${p2.clip.durationMs}ms not close to speech span ${speechMs}ms (want ${low}..${high})`)
    }
  }
  if (!p2.states.includes('calibrating')) throw new Error('phase2: never calibrated')
  if (!p2.states.includes('listening')) throw new Error('phase2: never reached "listening"')
  if (!p2.states.includes('capturing')) throw new Error('phase2: never reached "capturing"')

  out.ok = true
} catch (err) {
  out.error = String(err?.message || err)
} finally {
  await browser.close().catch(() => {})
  result(out)
  if (!out.ok) process.exit(1)
}
