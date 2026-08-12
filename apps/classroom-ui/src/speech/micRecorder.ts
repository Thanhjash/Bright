/**
 * Microphone capture. Framework-free, one utterance at a time.
 *
 *     const mic = createMicRecorder()
 *     await mic.start()          // getUserMedia + MediaRecorder
 *     const clip = await mic.stop()
 *
 * The stream is opened on the FIRST press and then held for the session. Two
 * reasons: `getUserMedia` costs 200–600 ms on a cold device, which would land
 * squarely inside the moment a child is already speaking; and every re-open is
 * another chance for the browser to re-prompt. `release()` exists for teardown.
 *
 * A held button that never receives its `pointerup` — the pointer left the
 * window, the tab lost focus, the teacher's hand slipped — would otherwise
 * record until the disk filled. `MAX_UTTERANCE_MS` is the backstop, and it is
 * set below Whisper's 30-second window because audio past that is discarded by
 * the model anyway.
 */

export type MicFailure =
  /** the user (or a policy) said no */
  | 'denied'
  /** there is no microphone, or it is in use elsewhere */
  | 'unavailable'
  /** this browser cannot record — no `MediaRecorder`, or an insecure origin */
  | 'unsupported'

export class MicError extends Error {
  readonly failure: MicFailure
  constructor(failure: MicFailure, message: string, options?: { cause?: unknown }) {
    super(message, options)
    this.name = 'MicError'
    this.failure = failure
  }
}

/** Whisper's window is 30 s. Anything beyond it is thrown away by the model. */
export const MAX_UTTERANCE_MS = 25_000

/** In preference order. The first one this browser admits to is used. */
const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
]

export interface Clip {
  audio: Blob
  /** wall-clock length of the take. The ONLY honest measure of "did they speak
   *  long enough" — an encoded blob's size measures loudness, not duration. */
  durationMs: number
}

export interface MicRecorder {
  /** Opens the stream if needed and begins recording. */
  start(onAutoStop: (reason: 'cap') => void): Promise<void>
  /** Stops and resolves with the clip. Resolves with `null` if not recording. */
  stop(): Promise<Clip | null>
  /** 0…1, RMS of the live input. 0 when not recording. */
  level(): number
  recording(): boolean
  /** Drops the stream and the audio graph. Safe to call repeatedly. */
  release(): void
}

export function createMicRecorder(): MicRecorder {
  let stream: MediaStream | null = null
  let recorder: MediaRecorder | null = null
  let chunks: Blob[] = []
  let capTimer: ReturnType<typeof setTimeout> | undefined
  let startedAt = 0

  let audioCtx: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let samples: Float32Array<ArrayBuffer> | null = null

  async function ensureStream(): Promise<MediaStream> {
    if (stream && stream.getAudioTracks().some((t) => t.readyState === 'live')) return stream

    if (typeof MediaRecorder === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      throw new MicError(
        'unsupported',
        'This browser cannot record audio here. A microphone needs https:// or localhost.',
      )
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
    } catch (cause) {
      const name = (cause as { name?: string } | null)?.name
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        throw new MicError(
          'denied',
          'The microphone is blocked. Allow it for this page in the browser address bar, then try again.',
          { cause },
        )
      }
      throw new MicError(
        'unavailable',
        'No microphone was available. Check it is plugged in and not held by another app.',
        { cause },
      )
    }

    attachMeter(stream)
    return stream
  }

  /**
   * A level meter, not a nicety: a muted or unplugged microphone records a
   * perfectly valid file of digital silence, Whisper returns "", and without
   * this the only symptom is a lesson that never advances.
   */
  function attachMeter(source: MediaStream): void {
    try {
      audioCtx = new AudioContext()
      analyser = audioCtx.createAnalyser()
      analyser.fftSize = 1024
      samples = new Float32Array(new ArrayBuffer(analyser.fftSize * 4))
      audioCtx.createMediaStreamSource(source).connect(analyser)
    } catch (cause) {
      // The meter is diagnostic. Losing it must not cost us the recording.
      console.warn('[voice] level meter unavailable', cause)
      analyser = null
    }
  }

  function pickMime(): string | undefined {
    return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported?.(m))
  }

  return {
    async start(onAutoStop) {
      if (recorder) return
      const live = await ensureStream()
      void audioCtx?.resume()

      const mimeType = pickMime()
      recorder = new MediaRecorder(live, mimeType ? { mimeType } : undefined)
      chunks = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }
      recorder.start()
      startedAt = performance.now()

      capTimer = setTimeout(() => {
        if (recorder?.state === 'recording') onAutoStop('cap')
      }, MAX_UTTERANCE_MS)
    },

    stop() {
      const active = recorder
      recorder = null
      clearTimeout(capTimer)
      capTimer = undefined
      if (!active || active.state === 'inactive') return Promise.resolve(null)

      const durationMs = performance.now() - startedAt
      return new Promise<Clip>((resolve) => {
        active.onstop = () => {
          resolve({
            audio: new Blob(chunks, { type: active.mimeType || 'audio/webm' }),
            durationMs,
          })
          chunks = []
        }
        active.stop()
      })
    },

    level() {
      if (!analyser || !samples || !recorder) return 0
      analyser.getFloatTimeDomainData(samples)
      let sum = 0
      for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i]
      // ×4 so ordinary classroom speech reaches the top of the meter rather
      // than nudging it; this is a "can you hear me" light, not a VU meter.
      return Math.min(1, Math.sqrt(sum / samples.length) * 4)
    },

    recording() {
      return recorder !== null
    },

    release() {
      clearTimeout(capTimer)
      capTimer = undefined
      try {
        recorder?.stop()
      } catch {
        // already inactive
      }
      recorder = null
      chunks = []
      stream?.getTracks().forEach((t) => t.stop())
      stream = null
      analyser = null
      samples = null
      void audioCtx?.close().catch(() => {})
      audioCtx = null
    },
  }
}
