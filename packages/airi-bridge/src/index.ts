/**
 * @bright/airi-bridge — a talking Live2D avatar for Bright.
 *
 * Ported from Project AIRI (https://github.com/moeru-ai/airi, MIT). See README.md
 * for what was vendored verbatim, what was rewritten, and why.
 *
 * Layers, from the bottom:
 *   src/vendor/  AIRI code, copied. Framework-free. Treat as read-only.
 *   src/act/     `<|ACT|>` / `<|DELAY|>` parsing. The correctness-critical part.
 *   src/live2d/  Live2D runtime. No React.
 *   src/speech/  text deltas → TTS → ordered playback → lip-sync. No React.
 *   src/react/   `<Live2DAvatar>` and `useSpeechPlayer`.
 *
 * The React layer is a thin wrapper. Everything below it can be used from any
 * framework, or from none.
 *
 * `./react` is a separate entry point so a non-React consumer never pulls React in.
 */

export * from './act'
export * from './live2d'
export * from './speech'

// Re-exported for convenience so consumers can import the contract types from one
// place. packages/contracts remains the single source of truth.
export type { ActPayload, Emotion } from './contracts'
export { EMOTION_MOTION_GROUP, EMOTIONS, TAG_CLOSE, TAG_OPEN, TAG_TAIL_RETAIN } from './contracts'

// Re-exported because you cannot call `createWebAudioBackend({ lipSyncProfile })`
// with types unless you can name the profile's type, and it lives in `wlipsync`.
// Without lipSyncProfile the mouth never moves, so this is not an optional
// corner of the API.
export type { Profile as LipSyncProfile } from 'wlipsync'
