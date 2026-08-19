/**
 * Voice gate — open-mic listening with energy VAD and endpointing.
 *
 * "The room listens when she is not speaking" (docs/decisions/2026-08-18-room-runs-itself.md).
 * A child cannot press a spacebar (NS-1: no adult decision on the critical
 * teaching path), so today's press/release contract in `micRecorder.ts` /
 * `RoomDock.tsx` cannot be the whole story. This module answers, on a tight
 * loop, the one question a held button used to answer for it: *is a child
 * talking right now, and have they stopped?* — and hands back a finished clip
 * in the exact shape `micRecorder.stop()` already returns, so `transcribe()`
 * in `stt.ts` needs no changes at all.
 *
 * It does **not** open a second microphone. It is handed the *same*
 * `MicRecorder` the caller already owns and drives it the way a held button
 * would: `prepare()` keeps one `getUserMedia` stream (and its RMS analyser,
 * see `micRecorder.ts` `attachMeter`) open; `start()`/`stop()` wrap only the
 * span it believes is speech. There must only ever be one microphone stream
 * in the page — this module leans on that, it does not re-implement it.
 *
 * Half-duplex is the single most important rule here (NORTH-STAR.md §5,
 * "Room": *Stage is the only loudspeaker*). While `useClassroom`'s
 * `avatar.speaking` is true — the same flag `speakingDriver.ts`'s
 * `onSpeakingChange` writes on every playback edge — the gate never opens,
 * and a capture already in flight is abandoned outright rather than sent to
 * Whisper. A trailing guard after speech ends absorbs room reverb before the
 * gate re-arms.
 *
 * Usage (not wired in here — the caller decides how this coexists with any
 * remaining manual hold-to-talk path):
 *
 *     const gate = createVoiceGate(mic.current, {
 *       onClip: (clip) => { ...same handling finishListen() gives a stopped clip... },
 *       onStateChange: (state) => { ...drive a light, if useful... },
 *       onError: (message, failure) => { ...show a fault, do not throw... },
 *     })
 *     gate.start()   // begins calibrating, then listening
 *     gate.stop()    // e.g. on unmount, or while a manual hold-to-talk is active
 */
import type { Clip, MicFailure, MicRecorder } from './micRecorder'
import { MicError } from './micRecorder'
import { useClassroom } from '../store/classroom'

// ---------------------------------------------------------------- tunables
//
// Every constant below came from a named, real failure. Changing one without
// re-reading its comment is how the gate goes back to inventing words or
// answering herself.

/** How often the gate samples `mic.level()` and re-evaluates its state.
 *  Bounds how late onset/offset detection can be — worst case it is this
 *  many ms late opening on a child's first syllable, or late closing after
 *  she stops. Push it much higher and endpointing visibly lags; push it much
 *  lower and this becomes a second animation loop, on a miniPC, purely to
 *  poll a number that barely moved. */
/** How long to wait before trying the microphone again after it fails.
 *  Too short and a denied permission spins; too long and a re-seated USB mic
 *  stays dead for most of a lesson. */
const RETRY_AFTER_ERROR_MS = 5000
const POLL_MS = 40

/** Trailing silence required before a captured utterance is considered
 *  finished. Too short and a mid-sentence breath — a real, observed failure
 *  — splits one question into two Whisper calls ("what is a" / "banana?").
 *  Too long and the room waits that much longer, after speech has actually
 *  stopped, before Whisper is even asked. Start here; raise only in a real
 *  reverberant room, never in a demo. */
const SILENCE_MS = 800

/** How long, at start-up (or after ungating), the gate only measures the
 *  room before it will ever open. Skip this and the very first ambient
 *  sound — a chair, a door, the projector fan spinning up — gets treated as
 *  speech, or worse, gets averaged in as "floor" a beat too early and the
 *  gate never opens on anything quieter than that transient again. */
const CALIBRATION_MS = 1000

/** Energy must clear `floor * OPEN_MULTIPLIER` to open the gate (begin a
 *  capture). Too low (near 1×) and ordinary room reverb right after Piper
 *  stops re-opens the gate on nothing; too high and a child speaking softly
 *  from the back of the room never trips it at all. */
const OPEN_MULTIPLIER = 2.2

/** Once open, energy must fall below `floor * CLOSE_MULTIPLIER` before the
 *  silence timer starts counting toward `SILENCE_MS`. Deliberately lower
 *  than `OPEN_MULTIPLIER` (hysteresis): without the gap, one syllable a
 *  notch quieter than the one that opened the gate would immediately start
 *  closing it mid-sentence. */
const CLOSE_MULTIPLIER = 1.5

/** Fraction the adaptive floor moves toward the current ambient reading on
 *  every sample taken while listening (never while capturing or gated).
 *  Too high and the floor chases a talking child upward mid-utterance,
 *  silently raising the bar she has to clear to keep being heard next time;
 *  too low and a classroom that gets noisier over the period (more children
 *  arrive, a fan starts) never re-calibrates and the gate jams open. */
const FLOOR_ADAPT_RATE = 0.02

/** The floor never adapts below this. `mic.level()` reads ~0 for digital
 *  silence — a muted or unplugged mic — and `OPEN_MULTIPLIER * 0` is still
 *  0, which would trip the gate on any nonzero noise at all. */
const MIN_FLOOR = 0.015

/** Same value `RoomDock.tsx` enforces today as `MIN_CLIP_MS`. Whisper
 *  `small` invents words on very short clips — `BANANO`, `Happy!` are real
 *  observed outputs on sub-600 ms takes. A finished capture shorter than
 *  this is dropped, never handed to `onClip`. */
const MIN_CLIP_MS = 600

/** Ceiling on one captured utterance, passed straight through to
 *  `mic.start()`'s own cap timer. The ASR endpoint rejects uploads over
 *  20 MB; at ordinary Opus bitrates 15 s stays far under that even for a
 *  noisy room that never triggers the silence timeout on its own. */
const MAX_CLIP_MS = 15_000

/** Held closed after `avatar.speaking` last read true, before the gate is
 *  even allowed to calibrate or listen again. Piper's own output plus room
 *  reverb keeps registering as energy for a few hundred ms after playback
 *  ends; open earlier than this and she starts hearing, and transcribing,
 *  herself — the whole reason half-duplex is rule one here. */
const POST_SPEECH_GUARD_MS = 400

// ------------------------------------------------------------------ types

export type VoiceGateState =
  /** `stop()` was called, or `start()` never was. */
  | 'idle'
  /** Measuring the room's ambient level before the gate is allowed to open. */
  | 'calibrating'
  /** Mic open, gate armed, nothing above the open threshold yet. */
  | 'listening'
  /** An utterance is being recorded. */
  | 'capturing'
  /** Half-duplex hold: she is speaking, or still inside the trailing guard. */
  | 'gated'
  /** The mic could not be opened at all. No VAD; `onError` already fired. */
  | 'error'

export interface VoiceGateOptions {
  /** Fires once per finished, accepted utterance — never for a clip shorter
   *  than `MIN_CLIP_MS`, and never for one abandoned mid-capture because she
   *  started speaking. The shape is exactly what `mic.stop()` returns, so it
   *  can be handed to `transcribe()` in `stt.ts` unchanged. */
  onClip: (clip: Clip) => void
  /** Every state transition. Optional — useful for a status light, nothing
   *  in the gate depends on it being observed. */
  onStateChange?: (state: VoiceGateState) => void
  /** A permission/device failure, or any other reason VAD degraded to no
   *  listening at all. Always reported here, **never thrown** — this must
   *  degrade the room, not crash the projector page. */
  onError?: (message: string, failure?: MicFailure) => void
}

export interface VoiceGate {
  /** Opens the mic (via the `MicRecorder` this gate was built with) and
   *  begins calibrating, then listening. A second call while already
   *  running is a no-op. Never throws — failures reach `onError`. */
  start(): void
  /** Stops listening. If a capture is in flight it is abandoned (its audio
   *  is discarded, `onClip` does not fire). Does not release the
   *  `MicRecorder`'s stream — that is the caller's to keep or tear down.
   *  Safe to call repeatedly, including before `start()`. */
  stop(): void
  /** The gate's current state, for a caller that wants to poll rather than
   *  subscribe. */
  state(): VoiceGateState
  /** The current adaptive noise floor (0…1, same units as `mic.level()`).
   *  Diagnostic / test hook, not required for normal use. */
  floor(): number
}

type CaptureState = 'idle' | 'starting' | 'capturing' | 'finalizing'

/**
 * Build a voice gate over an existing `MicRecorder`. Does not call
 * `createMicRecorder()` itself — pass the same instance the caller already
 * owns, so the page never opens two microphone streams.
 */
export function createVoiceGate(mic: MicRecorder, options: VoiceGateOptions): VoiceGate {
  let running = false
  let intervalId: ReturnType<typeof setInterval> | null = null
  let currentState: VoiceGateState = 'idle'

  let calibrated = false
  let calibrationStartedAt: number | null = null
  let calibrationSum = 0
  let calibrationCount = 0
  let floorLevel = MIN_FLOOR

  let guardUntil = 0
  let captureState: CaptureState = 'idle'
  let lastAboveCloseAt = 0

  let errorReported = false
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  function setState(next: VoiceGateState): void {
    if (currentState === next) return
    currentState = next
    options.onStateChange?.(next)
  }

  function reportError(err: unknown): void {
    if (errorReported) return
    errorReported = true
    if (err instanceof MicError) {
      options.onError?.(err.message, err.failure)
    } else {
      options.onError?.(err instanceof Error ? err.message : String(err))
    }
  }

  function resetCalibration(): void {
    calibrated = false
    calibrationStartedAt = null
    calibrationSum = 0
    calibrationCount = 0
  }

  function beginCapture(now: number): void {
    captureState = 'starting'
    lastAboveCloseAt = now
    mic.start(() => {
      // mic's own `MAX_UTTERANCE_MS`-style cap fired; `maxDurationMs` below
      // keeps that well inside MAX_CLIP_MS, so this is the normal "very
      // long utterance" path, not an error.
      void finalizeCapture()
    }, MAX_CLIP_MS).then(() => {
      if (captureState !== 'starting') return // stop()/gate closed while opening
      captureState = 'capturing'
      setState('capturing')
    }).catch((err: unknown) => {
      captureState = 'idle'
      reportError(err)
      setState(running ? 'listening' : 'idle')
    })
  }

  async function finalizeCapture(): Promise<void> {
    if (captureState !== 'starting' && captureState !== 'capturing') return
    captureState = 'finalizing'
    let clip: Clip | null = null
    try {
      clip = await mic.stop()
    } catch (err) {
      reportError(err)
    }
    captureState = 'idle'
    if (clip && clip.durationMs >= MIN_CLIP_MS) {
      options.onClip(clip)
    }
    setState(running ? 'listening' : 'idle')
  }

  /** Half-duplex violation guard, or an explicit `stop()`: throw the take
   *  away. Never reaches `onClip`. */
  async function abandonCapture(): Promise<void> {
    if (captureState === 'idle') return
    captureState = 'finalizing'
    try {
      await mic.stop()
    } catch {
      // best-effort; the recorder is being discarded either way
    }
    captureState = 'idle'
  }

  function tick(): void {
    try {
      tickUnsafe()
    } catch (err) {
      // Requirement: never throw into the render path. Degrade to idle and
      // report once, rather than let a bad sample crash the projector page.
      running = false
      if (intervalId !== null) {
        clearInterval(intervalId)
        intervalId = null
      }
      void abandonCapture()
      reportError(err)
      setState('error')
    }
  }

  function tickUnsafe(): void {
    if (!running) return
    const now = performance.now()
    const level = mic.level()

    const speakingNow = Boolean(useClassroom.getState().avatar.speaking)
    if (speakingNow) guardUntil = now + POST_SPEECH_GUARD_MS
    const gated = speakingNow || now < guardUntil

    if (gated) {
      if (captureState !== 'idle') void abandonCapture()
      resetCalibration()
      setState('gated')
      return
    }

    if (!calibrated) {
      if (calibrationStartedAt === null) {
        calibrationStartedAt = now
        calibrationSum = 0
        calibrationCount = 0
        setState('calibrating')
      }
      calibrationSum += level
      calibrationCount += 1
      if (now - calibrationStartedAt >= CALIBRATION_MS) {
        floorLevel = Math.max(MIN_FLOOR, calibrationSum / Math.max(1, calibrationCount))
        calibrated = true
        setState('listening')
      }
      return
    }

    if (captureState === 'starting' || captureState === 'finalizing') {
      // mid-transition; the async continuation above will move state on
      return
    }

    if (captureState === 'idle') {
      setState('listening')
      if (level > floorLevel * OPEN_MULTIPLIER) {
        beginCapture(now)
      } else {
        floorLevel = Math.max(MIN_FLOOR, floorLevel * (1 - FLOOR_ADAPT_RATE) + level * FLOOR_ADAPT_RATE)
      }
      return
    }

    // captureState === 'capturing'
    setState('capturing')
    if (level > floorLevel * CLOSE_MULTIPLIER) {
      lastAboveCloseAt = now
    } else if (now - lastAboveCloseAt >= SILENCE_MS) {
      void finalizeCapture()
    }
  }

  return {
    start() {
      if (running) return
      running = true
      errorReported = false
      resetCalibration()
      guardUntil = 0
      captureState = 'idle'
      setState('idle')
      const arm = () => {
        mic.prepare().then(() => {
          if (!running) return
          errorReported = false          // it recovered; let the next fault speak
          intervalId = setInterval(tick, POLL_MS)
        }).catch((err: unknown) => {
          if (!running) return
          reportError(err)
          setState('error')
          // Keep trying. A kiosk boots before the adult grants the microphone,
          // and a USB mic can be re-seated mid-lesson. Failing once and staying
          // deaf for the rest of the period is the worst outcome available:
          // the dock would go on inviting the class to speak into nothing.
          retryTimer = setTimeout(arm, RETRY_AFTER_ERROR_MS)
        })
      }
      arm()
    },

    stop() {
      running = false
      if (retryTimer !== null) {
        clearTimeout(retryTimer)
        retryTimer = null
      }
      if (intervalId !== null) {
        clearInterval(intervalId)
        intervalId = null
      }
      void abandonCapture()
      resetCalibration()
      setState('idle')
    },

    state() {
      return currentState
    },

    floor() {
      return floorLevel
    },
  }
}
