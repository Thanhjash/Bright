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

/** How long a capture may run without EVER dropping below the close
 *  threshold before the gate concludes its own floor is wrong.
 *
 *  Real speech has gaps -- between words, between clauses, to breathe. A
 *  capture where the level never once falls quiet is not a person talking
 *  without pause; it is a floor measured in a quieter room than the one we are
 *  now in. Observed 2026-08-21 with an air conditioner behind the child: the
 *  floor was calibrated during one quiet second at start-up, the fan then sat
 *  permanently above `floor * CLOSE_MULTIPLIER`, the silence timer never
 *  started, and every capture ran to MAX_CLIP_MS. Fifteen seconds of recording
 *  plus fourteen of transcription is half a minute before she hears anything --
 *  and fifteen seconds of fan is exactly what makes Whisper loop ("I like the
 *  power of the power of the power").
 *
 *  Long enough that a genuinely unbroken sentence is not cut short; short
 *  enough that a wrong floor costs seconds, not half a minute. */
const FLOOR_STALE_MS = 4000

/** Peak-to-trough ratio below which a capture is machinery, not a person.
 *
 *  A fan, a projector, a fridge hold a near-constant level; a child's voice
 *  swings between syllables and the gaps around them. 2.5x is comfortably
 *  under the range of ordinary speech and comfortably over the wobble of a
 *  motor, so it separates them without needing to know which room this is. */
const FLAT_NOISE_RATIO = 2.5

/** Trailing quiet that ends a PHRASE — cut a fragment, keep recording — as
 *  opposed to SILENCE_MS, which ends the TURN.
 *
 *  320ms is eight consecutive quiet ticks at POLL_MS=40. Inter-word gaps and
 *  stop-consonant closures run 50-150ms, so this does not fire inside a word;
 *  clause junctures and breaths run 300ms and up, which is exactly where a
 *  person expects the words so far to appear. Below ~250 you cut inside the
 *  /p/ of "stop" and hand Whisper a truncated word; above ~450 it almost never
 *  fires inside a Grade-3 answer and the whole level is dead weight. */
const PHRASE_SILENCE_MS = 320

/** A child who does not pause at all still has to see words. Without this,
 *  a run-on answer shows its first word only when the capture ends. 3500ms is
 *  about one primary-school sentence. */
const MAX_FRAGMENT_MS = 3500

/** No fragment is cut shorter than this by choice. Same reason MIN_CLIP_MS
 *  exists — Whisper invents `BANANO` on sub-600ms audio — and 700 rather than
 *  600 because a fragment, unlike a capture, carries no pre-roll of its own. */
const MIN_FRAGMENT_MS = 700

/** How far behind the transcriber may fall before the fragment stream gives
 *  up for this utterance. Four fragments is roughly fourteen seconds of
 *  un-transcribed audio: the box is losing, and the honest move is to stop
 *  cutting and let the final clip cover the rest. Never to DROP a fragment —
 *  a sentence with a hole in it is plausible and wrong, which is the worst
 *  failure available here. */
const MAX_QUEUED_FRAGMENTS = 4

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
  /**
   * A phrase, cut while the child is still speaking.
   *
   * Fires several times per utterance, in order, each covering a disjoint span
   * of the same recording. The caller transcribes them and shows the words as
   * they settle; the one flagged `last` means the turn is over.
   *
   * When this is provided the gate cuts phrases and `onClip` still fires at the
   * end with the whole utterance, so a caller can use either or both. When it
   * is absent nothing changes at all — the gate behaves exactly as before.
   */
  onFragment?: (fragment: VoiceFragment) => void
  /**
   * How many fragments are still waiting to be transcribed. The gate asks
   * before every cut and stops cutting for the rest of the utterance once the
   * queue is deep, rather than adding to a pile-up nobody is draining.
   */
  pendingFragments?: () => number
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

/** One phrase, cut while the child is still speaking. */
export interface VoiceFragment {
  audio: Blob
  durationMs: number
  /** Which utterance this belongs to. A fragment from a previous utterance
   *  that arrives late must never join the current sentence. */
  utteranceId: number
  /** Position within the utterance. The fragments of one utterance tile its
   *  audio in order with no gap and no overlap. */
  index: number
  /** True when this is the last fragment of its utterance — the turn is over
   *  and whatever has accumulated should be sent. */
  last: boolean
}

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
  /** Quietest level seen during the current capture, and when it began. Only
   *  used to notice that the floor has gone stale. */
  let captureMinLevel = Number.POSITIVE_INFINITY
  let captureMaxLevel = 0
  let captureOpenedAt = 0

  // ── the fragment stream ────────────────────────────────────────────────
  // Phrases are cut out of a capture that keeps running, so the child sees
  // words while still talking. Cutting is by SAMPLE INDEX (see
  // `mic.sliceSince`) so consecutive fragments tile the audio exactly.
  let utteranceId = 0
  let fragmentIndex = 0
  let nextFromSample = 0
  let lastCutAt = 0
  /** There is speech since the last cut that no fragment covers yet. When
   *  false at sentence end, no tail fragment is needed — which is the common
   *  case, and saves an entire Whisper call on every ordinary sentence. */
  let phraseArmed = false
  /** Turned off for the rest of an utterance when the transcriber falls
   *  behind. The capture continues; only the mid-sentence cutting stops. */
  let fragmentsEnabled = true
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
    captureMinLevel = Number.POSITIVE_INFINITY
    captureMaxLevel = 0
    captureOpenedAt = now
    utteranceId += 1
    fragmentIndex = 0
    nextFromSample = 0
    lastCutAt = now
    phraseArmed = false
    fragmentsEnabled = typeof options.onFragment === 'function'
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

  /**
   * Hand over everything recorded since the last cut, without stopping.
   *
   * `last` is the tail at sentence end. It MUST be taken before `mic.stop()` is
   * awaited: `stop()` releases the capture buffer, and a slice taken afterwards
   * returns null — which would silently lose the final words of every sentence.
   */
  function cutFragment(now: number, last: boolean): void {
    const emit = options.onFragment
    if (!emit) return
    const slice = mic.sliceSince(nextFromSample)
    if (!slice) return
    // A tail shorter than a syllable is Whisper's invention machine. Drop it
    // rather than show a word nobody said; the words before it still stand.
    if (slice.durationMs < MIN_FRAGMENT_MS && !last) return
    nextFromSample = slice.toSample
    lastCutAt = now
    phraseArmed = false
    emit({
      audio: slice.audio,
      durationMs: slice.durationMs,
      utteranceId,
      index: fragmentIndex++,
      last,
    })
  }

  async function finalizeCapture(): Promise<void> {
    if (captureState !== 'starting' && captureState !== 'capturing') return
    // BEFORE stop(). See cutFragment's note: stop() frees the buffer.
    // `phraseArmed` false means the last phrase cut already covered everything
    // said, and the quiet since then contains no words — so most sentences end
    // without a tail fragment and without an extra Whisper call.
    if (fragmentsEnabled && phraseArmed) cutFragment(performance.now(), true)
    else if (fragmentsEnabled && fragmentIndex > 0) options.onFragment?.({
      // Nothing left to transcribe, but the caller still has to be told the
      // sentence is finished so it can post the turn.
      audio: new Blob([], { type: 'audio/wav' }),
      durationMs: 0,
      utteranceId,
      index: fragmentIndex++,
      last: true,
    })
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
      // Do NOT throw the floor measurement away.
      //
      // This used to call `resetCalibration()` on every gated tick, which set
      // `calibrated = false` -- so the moment she stopped talking the room owed
      // POST_SPEECH_GUARD_MS (400) *plus a whole CALIBRATION_MS* (1000) before
      // the gate could open at all. A child who answers promptly, which is what
      // children do, was speaking into a microphone that was not listening yet,
      // and 300ms of pre-roll cannot cover 1.4 seconds. That is the literal
      // sense of "nó không bắt được âm thanh liền".
      //
      // The second bought nothing: `resetCalibration()` never cleared
      // `floorLevel`, so the old floor was sitting there unused the whole time,
      // and `FLOOR_ADAPT_RATE` keeps it tracking the room on every listening
      // tick anyway. Only calibrate when there has never been a floor.
      //
      // The 400ms guard stays -- her reverb is real, and it is the only thing
      // standing between her and transcribing herself.
      if (!calibrated) resetCalibration()
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
    captureMinLevel = Math.min(captureMinLevel, level)
    captureMaxLevel = Math.max(captureMaxLevel, level)
    const quietFor = now - lastAboveCloseAt
    if (level > floorLevel * CLOSE_MULTIPLIER) {
      lastAboveCloseAt = now
      phraseArmed = true
      if (now - captureOpenedAt >= FLOOR_STALE_MS) {
        // Nothing in this whole capture has been quiet enough to count as
        // silence. That is not what a person talking sounds like, so the floor
        // is measured against a room that no longer exists. Move it up to just
        // under the quietest thing actually heard -- so that moment WILL read
        // as silence next time -- and hand over what we have rather than
        // recording the fan for another eleven seconds.
        floorLevel = Math.max(MIN_FLOOR, (captureMinLevel / CLOSE_MULTIPLIER) * 1.1)
        // Was this a child over a fan, or just the fan?
        //
        // Raising the floor is right either way, but SENDING is not: a capture
        // of pure machinery costs another Whisper call and can come back with
        // invented words that get posted as a child's turn -- she then answers
        // something nobody said. Speech is modulated (syllables, gaps, stress);
        // machinery is flat. Dynamic range tells them apart with two numbers we
        // are already tracking.
        if (captureMaxLevel < captureMinLevel * FLAT_NOISE_RATIO) void abandonCapture()
        else void finalizeCapture()
      }
      return
    }

    if (quietFor >= SILENCE_MS) {
      // SENTENCE END. Checked before the phrase rule on purpose: at 800ms of
      // quiet we finalize, rather than cutting a phrase here and then
      // immediately finalizing an empty tail behind it.
      void finalizeCapture()
      return
    }

    if (!fragmentsEnabled || !phraseArmed) return

    // The transcriber is behind. Stop cutting for the rest of this utterance;
    // the capture carries on and the final clip covers everything uncut, so the
    // sentence still arrives whole — it just arrives all at once, which is
    // exactly today's behaviour. Never drop a fragment to catch up.
    if ((options.pendingFragments?.() ?? 0) >= MAX_QUEUED_FRAGMENTS) {
      fragmentsEnabled = false
      return
    }

    // PHRASE END: either they paused, or they have not paused for so long that
    // waiting any longer would mean showing nothing at all.
    const sinceCut = now - lastCutAt
    if (sinceCut >= MIN_FRAGMENT_MS && (quietFor >= PHRASE_SILENCE_MS || sinceCut >= MAX_FRAGMENT_MS)) {
      cutFragment(now, false)
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
