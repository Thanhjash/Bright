export type { AudioBackend, OpaqueAudioBackend, WebAudioBackendOptions } from './audio-backend'
export { asOpaqueBackend, createWebAudioBackend } from './audio-backend'

export type {
  SpeechPlayer,
  SpeechPlayerEvents,
  SpeechPlayerOptions,
  SpeechTurn,
} from './player'
export { createSpeechPlayer } from './player'
