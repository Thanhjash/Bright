/**
 * The audio backend seam.
 *
 * `createSpeechPlayer` owns ordering, chunking and special-token timing; it does not
 * know what a Web Audio graph is. Everything that touches `AudioContext` lives behind
 * this interface, so the ordering invariants in PROTOCOL.md §6 can be tested in Node
 * with a fake backend, and so an app can swap in `<audio>` or a native player.
 */

import type { Profile } from 'wlipsync'

import type { Live2DLipSync, Live2DLipSyncOptions } from '../vendor/model-driver-lipsync/live2d/index'

// NOTE: `createLive2DLipSync` is imported LAZILY, inside `ensureLipSync()`.
// `wlipsync` subclasses `AudioWorkletNode` at module scope, so a static import
// throws `ReferenceError: AudioWorkletNode is not defined` the moment this module is
// evaluated anywhere without Web Audio — server-side rendering, a Node test, a build
// step that touches the entry point. Deferring it to first use keeps the package
// importable everywhere and costs one dynamic import on the first utterance.

export interface AudioBackend<TAudio = AudioBuffer> {
  // NOTE: these are METHOD signatures, not property-with-function-type signatures.
  // The difference is deliberate: methods are bivariant in their parameters, so an
  // `AudioBackend<AudioBuffer>` is usable where an `AudioBackend<unknown>` is asked
  // for. Rewriting them as `decode: (bytes) => ...` makes the player generic-infect
  // every caller for no benefit.

  /** Turns encoded bytes from the TTS provider into whatever `play` consumes. */
  decode: (bytes: ArrayBuffer) => Promise<TAudio>
  /**
   * Plays one segment to completion.
   *
   * MUST resolve only when the audio has really finished, or when `signal` aborts.
   * Resolving early breaks PROTOCOL.md §6.3 — the segment's special token would fire
   * before the sentence it belongs to has been heard.
   *
   * MUST play for its full duration even when muted. Muting means gain 0, never
   * "skip"; see PROTOCOL.md §6.4.
   */
  play: (audio: TAudio, signal: AbortSignal) => Promise<void>
  /** Current mouth openness, 0…0.7. Written RAW to the model. Never rescale. */
  getMouthOpen: () => number
  /** 0 silences output without changing playback timing. */
  setMuted: (muted: boolean) => void
  isMuted: () => boolean
  /** Stops everything immediately. Safe to call twice. */
  dispose: () => void
}

/**
 * A backend whose audio type has been erased.
 *
 * `createSpeechPlayer` never inspects the decoded value — it only carries it from
 * `decode` to `play` — so it takes this. `asOpaqueBackend` is the one sanctioned
 * place where the erasure happens, instead of making every caller generic.
 */
export type OpaqueAudioBackend = AudioBackend<unknown>

export function asOpaqueBackend<TAudio>(backend: AudioBackend<TAudio>): OpaqueAudioBackend {
  // Safe by construction: the player treats the value as an opaque token. This is
  // the only cast in the speech layer, and it exists so `AudioBackend<TAudio>` can
  // stay honestly typed for backend authors.
  return backend as OpaqueAudioBackend
}

export interface WebAudioBackendOptions {
  /** Reused if given. Otherwise one is created on first use (autoplay policy). */
  audioContext?: AudioContext
  /** Where audio goes. Defaults to `context.destination`. */
  destination?: AudioNode
  /**
   * wLipSync profile. Pass the vendored
   * `src/vendor/model-driver-lipsync/shared/wlipsync/profile.json`.
   * Omit to run without lip-sync — `getMouthOpen()` then always returns 0.
   */
  lipSyncProfile?: Profile
  lipSyncOptions?: Live2DLipSyncOptions
  /** Output level when not muted. */
  volume?: number
  onError?: (error: Error) => void
}

/**
 * Web Audio implementation.
 *
 * Graph:
 *
 *   AudioBufferSourceNode ─┬─► GainNode ─► destination     (what you hear; muted = 0)
 *                          └─► wLipSync node               (what drives the mouth)
 *
 * The lip-sync tap is taken BEFORE the gain node deliberately. Muting must not stop
 * the avatar's mouth: PROTOCOL.md §6.4 exists because a frozen avatar is how muting
 * used to look broken. Mute changes what the room hears, nothing else.
 */
export function createWebAudioBackend(
  options: WebAudioBackendOptions = {},
): AudioBackend<AudioBuffer> {
  let context: AudioContext | undefined = options.audioContext
  let gain: GainNode | undefined
  let lipSync: Live2DLipSync | undefined
  let lipSyncPending: Promise<void> | undefined
  let muted = false
  let disposed = false
  const volume = options.volume ?? 1
  const activeSources = new Set<AudioBufferSourceNode>()

  function ensureContext(): AudioContext {
    if (!context) {
      const Ctor = (globalThis as unknown as { AudioContext?: typeof AudioContext }).AudioContext
      if (!Ctor)
        throw new Error('[airi-bridge] no AudioContext in this environment. Inject one, or use a different AudioBackend.')
      context = new Ctor()
    }
    if (!gain) {
      gain = context.createGain()
      gain.gain.value = muted ? 0 : volume
      gain.connect(options.destination ?? context.destination)
    }
    return context
  }

  function ensureLipSync(): Promise<void> {
    if (!options.lipSyncProfile || lipSync || disposed)
      return Promise.resolve()
    if (lipSyncPending)
      return lipSyncPending

    lipSyncPending = import('../vendor/model-driver-lipsync/live2d/index')
      .then(({ createLive2DLipSync }) => createLive2DLipSync(
        ensureContext(),
        options.lipSyncProfile!,
        options.lipSyncOptions,
      ))
      .then((created) => {
        lipSync = created
      })
      .catch((error) => {
        // No lip-sync is a degraded avatar, not a failed lesson. Warn once and carry on.
        console.warn('[airi-bridge] lip-sync worklet unavailable; the mouth will not move.', error)
        options.onError?.(error instanceof Error ? error : new Error(String(error)))
      })

    return lipSyncPending
  }

  return {
    async decode(bytes) {
      const ctx = ensureContext()
      // decodeAudioData detaches the buffer, so hand it a copy — the caller may
      // legitimately keep or retry with the original bytes.
      return await ctx.decodeAudioData(bytes.slice(0))
    },

    async play(audio, signal) {
      if (disposed || signal.aborted)
        return

      const ctx = ensureContext()
      await ensureLipSync()

      if (ctx.state === 'suspended')
        await ctx.resume().catch(() => undefined)

      if (signal.aborted)
        return

      const source = ctx.createBufferSource()
      source.buffer = audio
      source.connect(gain!)
      if (lipSync)
        lipSync.connectSource(source)

      activeSources.add(source)

      await new Promise<void>((resolve) => {
        let settled = false
        const finish = () => {
          if (settled)
            return
          settled = true
          signal.removeEventListener('abort', onAbort)
          activeSources.delete(source)
          try {
            source.disconnect()
          }
          catch {
            // already torn down
          }
          resolve()
        }
        const onAbort = () => {
          try {
            source.stop()
          }
          catch {
            // never started, or already stopped
          }
          finish()
        }

        source.onended = finish
        signal.addEventListener('abort', onAbort, { once: true })
        source.start()
      })
    },

    getMouthOpen() {
      // 0…0.7 by construction (the driver caps each vowel weight at 0.7).
      // Written raw to ParamMouthOpenY, which expects 0…1. Do NOT rescale.
      return lipSync?.getMouthOpen() ?? 0
    },

    setMuted(next) {
      muted = next
      if (gain)
        gain.gain.value = next ? 0 : volume
    },

    isMuted: () => muted,

    dispose() {
      if (disposed)
        return
      disposed = true
      for (const source of activeSources) {
        try {
          source.stop()
        }
        catch {
          // already stopped
        }
      }
      activeSources.clear()
      try {
        gain?.disconnect()
      }
      catch {
        // already disconnected
      }
      // Only close a context we created ourselves.
      if (context && !options.audioContext)
        void context.close().catch(() => undefined)
    },
  }
}
