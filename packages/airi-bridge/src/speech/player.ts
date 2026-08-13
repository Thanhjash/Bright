/**
 * `createSpeechPlayer` — text deltas in, ordered speech and ACT signals out.
 *
 * This is the wiring described in PROTOCOL.md §6. Almost none of the hard part is
 * written here: `createSpeechPipeline`, `createTtsSegmentStream` and
 * `createPlaybackManager` are vendored from AIRI unchanged and already carry the
 * invariants. What this module adds is the ACT-token front end, the injected TTS
 * function, and the audio backend seam.
 *
 * The invariants, and where each one actually lives:
 *
 *  1. Chunker `boost = 2` — first two segments bypass the minimum-word rule, so the
 *     avatar starts talking sooner. `vendor/.../tts-chunker.ts`, defaulted here.
 *  2. TTS runs 4-way concurrent, playback is scheduled strictly in TEXT order, and a
 *     failed segment stores `null` so the sequence gate advances instead of
 *     deadlocking. `vendor/.../speech-pipeline.ts` (`scheduleCompletedRequests`).
 *  3. A special token attached to a segment fires AFTER that segment's audio
 *     finishes. `vendor/.../speech-pipeline.ts` (`enqueuePlayback` awaits
 *     `waitForPlayback` before emitting `onSpecial`).
 *  4. Muting must still dispatch specials. This one is NOT in the vendored code —
 *     it is a property of the `play` function, and it is the reason
 *     `AudioBackend.play` is documented as "plays to completion even when muted".
 *     `createWebAudioBackend` implements mute as gain 0, never as a skip.
 *  5. `getMouthOpen()` returns 0…0.7 and is written RAW to `ParamMouthOpenY`.
 *     Passed through untouched.
 */

import type { ActSignal } from '../act'
import type { Emotion } from '../contracts'
import type { AudioBackend, AudioPlaybackStart } from './audio-backend'
import type {
  IntentOptions,
  TextSegment,
  TtsInputChunkOptions,
  TtsRequest,
} from '../vendor/pipelines-audio/index'

import { createMarkerParser, parseSignal, resolveEmotion } from '../act'
import { createPlaybackManager, createSpeechPipeline, createTtsSegmentStream } from '../vendor/pipelines-audio/index'

export interface SpeechPlayerEvents {
  /** A control token, after its segment's audio finished. */
  onSignal?: (signal: ActSignal, segment: TextSegment) => void
  /** Convenience view of an ACT token's emotion. Fires after `onSignal`. */
  onEmotion?: (emotion: Emotion, intensity: number, segment: TextSegment) => void
  /** A `<|DELAY n|>` token. The player does NOT sleep — the caller decides. */
  onDelay?: (seconds: number, segment: TextSegment) => void
  /** Every segment as it is chunked, before TTS. Useful for subtitles. */
  onSegment?: (segment: TextSegment) => void
  /** Segment audio started at the output backend. */
  onSegmentStart?: (segment: {
    text: string
    segmentId: string
    turnId?: string
    audioContextTime?: number
  }) => void
  /** Speaking / not speaking. Drives the lip-sync release tail. */
  onSpeakingChange?: (speaking: boolean) => void
  onTurnStart?: (turnId: string) => void
  onTurnEnd?: (turnId: string) => void
  onTurnCancel?: (turnId: string, reason?: string) => void
  onError?: (error: Error, context?: { segmentId: string, turnId?: string }) => void
}

// Generic over the backend's decoded-audio type.
//
// It was `AudioBackend<unknown>`, which looks permissive but is the opposite:
// `AudioBackend<AudioBuffer>` is not assignable to it, because `play(audio: T)`
// makes T contravariant. Passing the Web Audio backend — the only backend that
// ships — failed to typecheck at every call site.
export interface SpeechPlayerOptions<TAudio = unknown> extends SpeechPlayerEvents {
  /**
   * The TTS call. Injected so the app picks the provider — the bridge never knows
   * about Piper, ElevenLabs or a `/audio/speech` endpoint.
   *
   * Returns encoded audio bytes (whatever the backend can decode). Throw or return
   * an empty buffer to skip a segment; the sequence gate advances either way.
   */
  tts: (
    text: string,
    context: { segmentId: string, turnId?: string },
    signal: AbortSignal,
  ) => Promise<ArrayBuffer>
  audio: AudioBackend<TAudio>
  /**
   * Concurrent TTS generations. PROTOCOL.md §6.2 says 4.
   *
   * @default 4
   */
  ttsMaxConcurrent?: number
  /**
   * Chunker tuning. `boost` defaults to 2 per PROTOCOL.md §6.1 — do not lower it
   * without measuring time-to-first-audio.
   */
  chunker?: TtsInputChunkOptions
}

export interface SpeechTurn {
  turnId: string
  /**
   * Feeds one streamed text delta. ALWAYS await it: the ACT parser applies
   * back-pressure here, and PROTOCOL.md §5.3 depends on it.
   */
  push: (delta: string) => Promise<void>
  /** No more text. Flushes the parser tail and lets the turn drain. */
  end: () => Promise<void>
  /** Stops this turn now. Queued audio is dropped, pending specials are not fired. */
  cancel: (reason?: string) => void
}

export interface SpeechPlayer {
  /** Opens a turn. Turns queue by default; pass `behavior` to interrupt or replace. */
  speak: (options?: IntentOptions) => SpeechTurn
  /** True from the first segment's audio start until the last one ends. */
  isSpeaking: () => boolean
  /** 0…0.7, raw. Feed straight to `Live2DStage.setMouthOpen`. */
  getMouthOpen: () => number
  setMuted: (muted: boolean) => void
  isMuted: () => boolean
  /** Cancels everything in flight. */
  stopAll: (reason?: string) => void
  dispose: () => void
}

export function createSpeechPlayer<TAudio>(options: SpeechPlayerOptions<TAudio>): SpeechPlayer {
  const backend = options.audio
  const chunkerOptions: TtsInputChunkOptions = { boost: 2, ...options.chunker }

  // `speaking` is per UTTERANCE, not per segment.
  //
  // `activeCount` alone flaps: it hits 0 in the gap between one segment's audio
  // ending and the next being scheduled off the timeline. Reporting that gap as
  // "not speaking" restarts `useMotionUpdatePluginLipSync`'s 200 ms release tail and
  // its 500 ms mouth-close handoff between every clause, so the mouth stutters shut
  // mid-sentence. Verified: a three-sentence utterance emitted
  // [true,false,true,false,true,false] before this was fixed.
  //
  // So speaking only ends when there is no audio playing AND no intent still
  // running. The pipeline emits onIntentEnd only after `timeline.flush('speech')`,
  // i.e. after the last segment has really finished, which makes this exact.
  let activeCount = 0
  let activeIntents = 0
  let speaking = false

  function setSpeaking(next: boolean) {
    if (speaking === next)
      return
    speaking = next
    options.onSpeakingChange?.(next)
  }

  function stopSpeakingIfIdle() {
    if (activeCount === 0 && activeIntents === 0)
      setSpeaking(false)
  }

  const playback = createPlaybackManager<TAudio>({
    maxVoices: 1,
    overflowPolicy: 'queue',
    // Muting never short-circuits this. The audio plays for its full duration at
    // gain 0, so the special token attached to the segment still fires on time.
    play: async (item, signal) => {
      let started = false
      const onStarted = (start: AudioPlaybackStart) => {
        if (started)
          return
        started = true
        activeCount += 1
        setSpeaking(true)
        options.onSegmentStart?.({
          text: item.text,
          segmentId: item.segmentId,
          turnId: item.turnId,
          ...start,
        })
      }
      try {
        await backend.play(item.audio, signal, { onStarted })
      }
      finally {
        if (started) {
          activeCount -= 1
          stopSpeakingIfIdle()
        }
      }
    },
  })

  const pipeline = createSpeechPipeline<TAudio>({
    ttsMaxConcurrent: options.ttsMaxConcurrent ?? 4,
    // Bound here rather than left to the caller so `boost: 2` cannot be lost.
    segmenter: (tokens, meta) => createTtsSegmentStream(tokens, meta, chunkerOptions),
    playback: {
      schedule: item => playback.schedule(item),
      stopAll: reason => playback.stopAll(reason),
      stopByIntent: (intentId, reason) => playback.stopByIntent(intentId, reason),
      stopByOwner: (ownerId, reason) => playback.stopByOwner(ownerId, reason),
      onStart: listener => void playback.onStart(listener),
      onEnd: listener => void playback.onEnd(listener),
      onInterrupt: listener => void playback.onInterrupt(listener),
      onReject: listener => void playback.onReject(listener),
    },
    tts: async (request: TtsRequest, signal: AbortSignal) => {
      if (!request.text.trim())
        return null
      try {
        const bytes = await options.tts(request.text, {
          segmentId: request.segmentId,
          turnId: request.turnId,
        }, signal)
        if (signal.aborted || !bytes || bytes.byteLength === 0)
          return null
        return await backend.decode(bytes)
      }
      catch (error) {
        if (signal.aborted)
          return null
        // Returning null (not throwing) is what keeps the sequence gate moving.
        // PROTOCOL.md §6.2: a failed segment must not deadlock the rest of the turn.
        const wrapped = error instanceof Error ? error : new Error(String(error))
        console.warn('[airi-bridge] TTS failed for a segment; skipping it.', wrapped)
        options.onError?.(wrapped, { segmentId: request.segmentId, turnId: request.turnId })
        return null
      }
    },
  })

  pipeline.on('onSegment', segment => options.onSegment?.(segment))
  pipeline.on('onTurnStart', turnId => options.onTurnStart?.(turnId))
  pipeline.on('onTurnEnd', turnId => options.onTurnEnd?.(turnId))
  pipeline.on('onTurnCancel', ({ turnId, reason }) => options.onTurnCancel?.(turnId, reason))

  pipeline.on('onIntentStart', () => {
    activeIntents += 1
  })
  pipeline.on('onIntentEnd', () => {
    activeIntents = Math.max(0, activeIntents - 1)
    stopSpeakingIfIdle()
  })
  pipeline.on('onIntentCancel', () => {
    activeIntents = Math.max(0, activeIntents - 1)
    stopSpeakingIfIdle()
  })

  pipeline.on('onSpecial', (segment) => {
    if (!segment.special)
      return

    const signal = parseSignal(segment.special)
    options.onSignal?.(signal, segment)

    if (signal.kind === 'act') {
      const emotion = resolveEmotion(signal.act)
      if (emotion)
        options.onEmotion?.(emotion.name, emotion.intensity, segment)
    }
    else if (signal.kind === 'delay') {
      options.onDelay?.(signal.seconds, segment)
    }
  })

  return {
    speak(intentOptions) {
      const handle = pipeline.openIntent(intentOptions)

      // Text goes through the ACT parser first, so a token split across two SSE
      // chunks can never reach the chunker as spoken text.
      const parser = createMarkerParser(async (event) => {
        if (event.type === 'literal')
          handle.writeLiteral(event.text)
        else
          handle.writeSpecial(event.raw)
      })

      return {
        turnId: handle.turnId ?? handle.intentId,
        async push(delta) {
          await parser.consume(delta)
        },
        async end() {
          await parser.end()
          handle.end()
        },
        cancel(reason) {
          parser.reset()
          handle.cancel(reason)
        },
      }
    },

    isSpeaking: () => speaking,
    getMouthOpen: () => backend.getMouthOpen(),
    setMuted: muted => backend.setMuted(muted),
    isMuted: () => backend.isMuted(),

    stopAll(reason = 'stop-all') {
      pipeline.stopAll(reason)
      activeIntents = 0
      setSpeaking(false)
    },

    dispose() {
      pipeline.stopAll('dispose')
      backend.dispose()
      activeIntents = 0
      setSpeaking(false)
    },
  }
}
