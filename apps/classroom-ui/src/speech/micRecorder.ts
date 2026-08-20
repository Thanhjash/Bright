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
import { MIC_LABELS } from '../room/labels'
export type MicFailure =
  /** the user (or a policy) said no */
  | 'denied'
  /** there is no microphone, or it is in use elsewhere */
  | 'unavailable'
  /** this browser cannot record — no `MediaRecorder`, or an insecure origin */
  | 'unsupported'
  /** the selected answer-station device disappeared after setup */
  | 'device_lost'
  /** a permission that had already been granted was revoked */
  | 'permission_lost'

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
  /** Opens and meters the answer-station mic without beginning a take. */
  prepare(): Promise<void>
  /** Opens the stream if needed and begins recording. */
  start(onAutoStop: (reason: 'cap') => void, maxDurationMs?: number): Promise<void>
  /** Stops and resolves with the clip. Resolves with `null` if not recording. */
  stop(): Promise<Clip | null>
  /** 0…1, RMS of the live input. 0 when not recording. */
  level(): number
  recording(): boolean
  /** Drops the stream and the audio graph. Safe to call repeatedly. */
  release(): void
}

/** How much audio to keep behind the gate. 300ms covers a soft onset like the
 *  /f/ in "Fine" without dragging in the tail of whatever came before. */
const PRE_ROLL_MS = 300
/** Ring length. Longer than any single utterance the gate will allow, so the
 *  pre-roll is always available and the memory cost stays a few hundred KB. */
const RING_SECONDS = 3

export function createMicRecorder(onDeviceFailure?: (failure: MicFailure) => void): MicRecorder {
  let stream: MediaStream | null = null
  let recorder: MediaRecorder | null = null
  let chunks: Blob[] = []
  let capTimer: ReturnType<typeof setTimeout> | undefined
  let startedAt = 0

  let audioCtx: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  // ── Pre-roll ────────────────────────────────────────────────────────────
  // THE BUG THIS EXISTS FOR. The gate opens when energy clears a threshold,
  // and only then was `start()` called -- so the sound that OPENED the gate
  // was the one sound never recorded. Observed with a real person on
  // 2026-08-20: "Fine, thank you." came back from Whisper as "Thank you."
  // every time. The model was innocent; the audio did not contain the word.
  //
  // So the graph now records continuously into a ring, and a clip begins
  // PRE_ROLL_MS *before* the gate said so. Nothing is uploaded from the ring
  // unless a capture is running -- it is a few seconds of memory, never a
  // recording of the room.
  let tap: ScriptProcessorNode | null = null
  let ring: Float32Array | null = null
  let ringWrite = 0
  let ringFilled = 0
  let ringRate = 48000
  let captureFrom = -1
  let samples: Float32Array<ArrayBuffer> | null = null
  let watchedTrack: MediaStreamTrack | null = null
  let permission: PermissionStatus | null = null
  let deviceWatchInstalled = false
  let failureReported: MicFailure | null = null

  const reportDeviceFailure = (failure: MicFailure) => {
    if (failureReported === failure) return
    failureReported = failure
    onDeviceFailure?.(failure)
  }

  const trackEnded = () => reportDeviceFailure('device_lost')
  const permissionChanged = () => {
    if (permission?.state === 'denied') reportDeviceFailure('permission_lost')
  }
  const devicesChanged = () => {
    const track = watchedTrack
    const selected = track?.getSettings().deviceId
    if (!track || track.readyState !== 'live') {
      reportDeviceFailure('device_lost')
      return
    }
    if (!selected) return
    void navigator.mediaDevices.enumerateDevices().then((devices) => {
      const stillPresent = devices.some((device) => device.kind === 'audioinput' && device.deviceId === selected)
      if (!stillPresent) reportDeviceFailure('device_lost')
    }).catch(() => {
      // Enumeration may be policy-blocked even while an already-open track is
      // healthy. The track's `ended` event remains the authoritative signal.
    })
  }

  function removeDeviceWatches(): void {
    watchedTrack?.removeEventListener('ended', trackEnded)
    watchedTrack = null
    permission?.removeEventListener('change', permissionChanged)
    permission = null
    if (deviceWatchInstalled) {
      navigator.mediaDevices?.removeEventListener?.('devicechange', devicesChanged)
      deviceWatchInstalled = false
    }
  }

  function installDeviceWatches(source: MediaStream): void {
    removeDeviceWatches()
    watchedTrack = source.getAudioTracks()[0] ?? null
    watchedTrack?.addEventListener('ended', trackEnded)
    if (navigator.mediaDevices?.addEventListener) {
      navigator.mediaDevices.addEventListener('devicechange', devicesChanged)
      deviceWatchInstalled = true
    }
    if (navigator.permissions?.query) {
      void navigator.permissions.query({ name: 'microphone' as PermissionName }).then((status) => {
        permission = status
        permission.addEventListener('change', permissionChanged)
      }).catch(() => {
        // Firefox and some Chromium policies do not expose microphone through
        // Permissions API. getUserMedia and track events still cover the path.
      })
    }
  }

  async function ensureStream(): Promise<MediaStream> {
    if (stream && stream.getAudioTracks().some((t) => t.readyState === 'live')) return stream

    if (typeof MediaRecorder === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      throw new MicError(
        'unsupported',
        'Trình duyệt này không ghi âm được ở đây — cần https:// hoặc localhost. '
        + '(This browser cannot record audio here.)',
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
        throw new MicError('denied', MIC_LABELS.blocked, { cause })
      }
      throw new MicError('unavailable', MIC_LABELS.missing, { cause })
    }

    failureReported = null
    installDeviceWatches(stream)
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
      const src = audioCtx.createMediaStreamSource(source)
      src.connect(analyser)
      // ScriptProcessor rather than an AudioWorklet: a worklet needs a second
      // file served at a URL, and this runs in a kiosk on a projector where
      // one fewer moving part is worth more than the deprecation notice.
      ringRate = audioCtx.sampleRate
      ring = new Float32Array(Math.ceil(ringRate * RING_SECONDS))
      ringWrite = 0
      ringFilled = 0
      tap = audioCtx.createScriptProcessor(4096, 1, 1)
      tap.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0)
        const buf = ring
        if (!buf) return
        for (let i = 0; i < input.length; i++) {
          buf[ringWrite] = input[i]
          ringWrite = (ringWrite + 1) % buf.length
        }
        ringFilled = Math.min(buf.length, ringFilled + input.length)
      }
      src.connect(tap)
      // A ScriptProcessor only runs while connected to a destination. Route it
      // through a muted gain so nothing is ever played back into the room --
      // the Stage is the only loudspeaker (half-duplex).
      const mute = audioCtx.createGain()
      mute.gain.value = 0
      tap.connect(mute)
      mute.connect(audioCtx.destination)
    } catch (cause) {
      // The meter is diagnostic. Losing it must not cost us the recording.
      console.warn('[voice] level meter unavailable', cause)
      analyser = null
    }
  }

  /** Ring slice from `from` to now, as a 16-bit mono WAV the ASR already eats. */
  function readRing(from: number): Blob | null {
    const buf = ring
    if (!buf) return null
    const length = (ringWrite - from + buf.length) % buf.length
    if (length < 1) return null
    const out = new Int16Array(length)
    for (let i = 0; i < length; i++) {
      const v = buf[(from + i) % buf.length]
      out[i] = Math.max(-32768, Math.min(32767, Math.round(v * 32767)))
    }
    const header = new ArrayBuffer(44)
    const view = new DataView(header)
    const put = (off: number, text: string) => {
      for (let i = 0; i < text.length; i++) view.setUint8(off + i, text.charCodeAt(i))
    }
    const bytes = out.length * 2
    put(0, 'RIFF'); view.setUint32(4, 36 + bytes, true); put(8, 'WAVE')
    put(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true)
    view.setUint16(22, 1, true); view.setUint32(24, ringRate, true)
    view.setUint32(28, ringRate * 2, true); view.setUint16(32, 2, true)
    view.setUint16(34, 16, true); put(36, 'data'); view.setUint32(40, bytes, true)
    return new Blob([header, out.buffer], { type: 'audio/wav' })
  }

  function pickMime(): string | undefined {
    return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported?.(m))
  }

  return {
    async prepare() {
      await ensureStream()
      void audioCtx?.resume()
    },

    async start(onAutoStop, maxDurationMs = MAX_UTTERANCE_MS) {
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
      // Begin the clip BEFORE the gate said so. This is the whole fix.
      if (ring) {
        const back = Math.min(ringFilled, Math.round(ringRate * PRE_ROLL_MS / 1000))
        captureFrom = (ringWrite - back + ring.length) % ring.length
      }

      capTimer = setTimeout(() => {
        if (recorder?.state === 'recording') onAutoStop('cap')
      }, Math.max(500, Math.min(MAX_UTTERANCE_MS, maxDurationMs)))
    },

    stop() {
      const active = recorder
      recorder = null
      clearTimeout(capTimer)
      capTimer = undefined
      if (!active || active.state === 'inactive') return Promise.resolve(null)

      const durationMs = performance.now() - startedAt
      const from = captureFrom
      captureFrom = -1
      return new Promise<Clip>((resolve) => {
        active.onstop = () => {
          // The ring is the good clip: it starts before the gate opened, so it
          // still has the word that opened it. The MediaRecorder blob is the
          // fallback for a browser with no AudioContext, and it is the one
          // that loses the first word.
          const pcm = from >= 0 ? readRing(from) : null
          resolve({
            audio: pcm ?? new Blob(chunks, { type: active.mimeType || 'audio/webm' }),
            durationMs,
          })
          chunks = []
        }
        active.stop()
      })
    },

    level() {
      if (!analyser || !samples) return 0
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
      removeDeviceWatches()
      stream?.getTracks().forEach((t) => t.stop())
      stream = null
      analyser = null
      samples = null
      void audioCtx?.close().catch(() => {})
      audioCtx = null
      try {
        tap?.disconnect()
      } catch {
        // already gone with the context
      }
      tap = null
      ring = null
      ringWrite = 0
      ringFilled = 0
      captureFrom = -1
    },
  }
}
