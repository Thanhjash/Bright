/**
 * `useSpeechPlayer` — the React face of `createSpeechPlayer`.
 *
 * Two things matter about the shape:
 *
 *  1. `getMouthOpen` is a STABLE FUNCTION, not state. It is read once per animation
 *     frame by `<Live2DAvatar>`; putting it in React state would re-render the tree
 *     sixty times a second.
 *  2. `speaking` IS state, because it changes twice per utterance and the UI (and the
 *     lip-sync release tail) needs to react to it.
 *
 * All handlers are held in a ref so changing one never tears down the audio graph.
 */

import type { ActSignal } from '../act'
import type { Emotion } from '../contracts'
import type { AudioBackend } from '../speech'
import type { SpeechPlayer, SpeechPlayerEvents, SpeechTurn } from '../speech'
import type { TextSegment, TtsInputChunkOptions } from '../vendor/pipelines-audio/index'
import type { Profile } from 'wlipsync'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { asOpaqueBackend, createSpeechPlayer, createWebAudioBackend } from '../speech'

export interface UseSpeechPlayerOptions extends SpeechPlayerEvents {
  /**
   * The TTS call. Injected so the app chooses the provider.
   * `(text) => Promise<ArrayBuffer>` of encoded audio.
   */
  tts: (
    text: string,
    context: { segmentId: string, turnId?: string },
    signal: AbortSignal,
  ) => Promise<ArrayBuffer>
  /** Supply a backend to take full control. Otherwise a Web Audio one is built. */
  audio?: AudioBackend<unknown>
  /** Reuse an existing context (e.g. one already unlocked by a user gesture). */
  audioContext?: AudioContext
  destination?: AudioNode
  /**
   * wLipSync profile. Import the vendored one:
   * `import profile from '@bright/airi-bridge/wlipsync-profile.json'`.
   * Without it the mouth stays shut.
   */
  lipSyncProfile?: Profile
  volume?: number
  muted?: boolean
  ttsMaxConcurrent?: number
  chunker?: TtsInputChunkOptions
}

export interface UseSpeechPlayerResult {
  /** Opens a turn. Feed deltas with `push`, finish with `end`. */
  speak: SpeechPlayer['speak']
  /**
   * Convenience for a complete string: opens a turn, pushes, ends.
   * Resolves when the text has been accepted, NOT when the audio finishes.
   */
  say: (text: string, turnId?: string) => Promise<SpeechTurn>
  /** True for the whole utterance. Pass to `<Live2DAvatar speaking>`. */
  speaking: boolean
  /** Stable across renders. Pass to `<Live2DAvatar getMouthOpen>`. Returns 0…0.7. */
  getMouthOpen: () => number
  /** Latest emotion seen on an ACT token. Pass to `<Live2DAvatar emotion>`. */
  emotion: Emotion | undefined
  setMuted: (muted: boolean) => void
  muted: boolean
  stopAll: (reason?: string) => void
  /** The underlying player, for anything this hook does not surface. */
  player: () => SpeechPlayer | null
}

export function useSpeechPlayer(options: UseSpeechPlayerOptions): UseSpeechPlayerResult {
  const optionsRef = useRef(options)
  optionsRef.current = options

  const playerRef = useRef<SpeechPlayer | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [emotion, setEmotion] = useState<Emotion | undefined>(undefined)
  const [muted, setMutedState] = useState(options.muted ?? false)

  // The audio graph is built once. Nothing in `options` may rebuild it — the handlers
  // are read through `optionsRef` at call time instead.
  const injectedAudio = options.audio
  const audioContext = options.audioContext
  const destination = options.destination
  const lipSyncProfile = options.lipSyncProfile

  useEffect(() => {
    const backend = injectedAudio ?? asOpaqueBackend(createWebAudioBackend({
      audioContext,
      destination,
      lipSyncProfile,
      volume: optionsRef.current.volume,
      onError: error => optionsRef.current.onError?.(error),
    }))

    const player = createSpeechPlayer({
      audio: backend,
      ttsMaxConcurrent: optionsRef.current.ttsMaxConcurrent,
      chunker: optionsRef.current.chunker,
      tts: (text, context, signal) => optionsRef.current.tts(text, context, signal),
      onSpeakingChange: (next) => {
        setSpeaking(next)
        optionsRef.current.onSpeakingChange?.(next)
      },
      onSignal: (signal: ActSignal, segment: TextSegment) => {
        optionsRef.current.onSignal?.(signal, segment)
      },
      onEmotion: (next, intensity, segment) => {
        setEmotion(next)
        optionsRef.current.onEmotion?.(next, intensity, segment)
      },
      onDelay: (seconds, segment) => optionsRef.current.onDelay?.(seconds, segment),
      onSegment: segment => optionsRef.current.onSegment?.(segment),
      onSegmentStart: segment => optionsRef.current.onSegmentStart?.(segment),
      onTurnStart: turnId => optionsRef.current.onTurnStart?.(turnId),
      onTurnEnd: turnId => optionsRef.current.onTurnEnd?.(turnId),
      onTurnCancel: (turnId, reason) => optionsRef.current.onTurnCancel?.(turnId, reason),
      onError: (error, context) => optionsRef.current.onError?.(error, context),
    })

    player.setMuted(optionsRef.current.muted ?? false)
    playerRef.current = player

    return () => {
      playerRef.current = null
      player.dispose()
    }
  }, [injectedAudio, audioContext, destination, lipSyncProfile])

  // Keep the graph in step with a controlled `muted` prop.
  const controlledMuted = options.muted
  useEffect(() => {
    if (controlledMuted === undefined)
      return
    setMutedState(controlledMuted)
    playerRef.current?.setMuted(controlledMuted)
  }, [controlledMuted])

  const speak = useCallback<SpeechPlayer['speak']>((intentOptions) => {
    const player = playerRef.current
    if (!player) {
      // Before mount or after unmount. Return an inert turn rather than throwing:
      // a stray delta must not take a lesson down.
      return {
        turnId: intentOptions?.turnId ?? 'detached',
        push: async () => {},
        end: async () => {},
        cancel: () => {},
      }
    }
    return player.speak(intentOptions)
  }, [])

  const say = useCallback(async (text: string, turnId?: string) => {
    const turn = speak(turnId ? { turnId } : undefined)
    await turn.push(text)
    await turn.end()
    return turn
  }, [speak])

  // Stable identity: this is called once per animation frame.
  const getMouthOpen = useCallback(() => playerRef.current?.getMouthOpen() ?? 0, [])

  const setMuted = useCallback((next: boolean) => {
    setMutedState(next)
    playerRef.current?.setMuted(next)
  }, [])

  const stopAll = useCallback((reason?: string) => {
    playerRef.current?.stopAll(reason)
  }, [])

  const player = useCallback(() => playerRef.current, [])

  return useMemo(() => ({
    speak,
    say,
    speaking,
    getMouthOpen,
    emotion,
    setMuted,
    muted,
    stopAll,
    player,
  }), [speak, say, speaking, getMouthOpen, emotion, setMuted, muted, stopAll, player])
}
