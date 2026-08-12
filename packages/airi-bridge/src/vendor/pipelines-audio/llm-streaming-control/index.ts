/**
 * Vendored from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/pipelines-audio/src/llm-streaming-control/index.ts
 * Version: 0.11.3 (commit b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Copied with the minimal deviations noted below. Do not otherwise edit.
 *
 * Deviation: re-export surface only. `./controller` replaces the upstream
 * `./index` self-import used by the upstream test file.
 */
export { createStreamingControlParser } from './controller'
export { normalizeActPayload } from './payloads'
export type {
  NormalizedActPayload,
  StreamingControlEmotion,
  StreamingControlEmotionPayload,
} from './payloads'
export { tokenAct, tokenCall, tokenDelay } from './parsers'
export type {
  LlmStreamingControl,
  LlmStreamingControlCallContext,
  LlmStreamingControlCallHandler,
  LlmStreamingControlCallManifest,
  LlmStreamingControlDispatchContext,
  LlmStreamingControlDispatchEvent,
  LlmStreamingControlDispatchObserver,
  LlmStreamingControlOptions,
  LlmStreamingControlParser,
  LlmStreamingControlSignal,
  LlmStreamingControlSignalContext,
  LlmStreamingControlSignalHandler,
  LlmStreamingControlTokenAct,
  LlmStreamingControlTokenCall,
  LlmStreamingControlTokenDelay,
} from './types'
