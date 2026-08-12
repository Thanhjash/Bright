/**
 * Everything under `src/vendor/` is copied from Project AIRI
 * (https://github.com/moeru-ai/airi, MIT, v0.11.3 @ b230e16) and is
 * framework-free — zero Vue, Pinia or @vueuse imports.
 *
 * Every file carries a header naming its upstream path and any deviation.
 * Treat this tree as read-only: to change behaviour, wrap it in `src/act`,
 * `src/live2d` or `src/react` instead of editing here.
 *
 * NOTE: the wLipSync driver is deliberately NOT re-exported here. `wlipsync`
 * subclasses `AudioWorkletNode` at module scope, so re-exporting it would make this
 * barrel throw on import in Node or during server-side rendering. Import it from its
 * own browser-only entry point instead:
 *
 *   import { createLive2DLipSync } from '@bright/airi-bridge/lipsync'
 *
 * Types are safe to take from here.
 */

export type {
  Live2DLipSync,
  Live2DLipSyncOptions,
  VowelKey,
} from './model-driver-lipsync/live2d/index'

export * from './pipelines-audio/index'
export * from './stream-kit/queue'
