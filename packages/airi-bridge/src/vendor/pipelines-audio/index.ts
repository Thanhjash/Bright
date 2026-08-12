/**
 * Vendored from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/pipelines-audio/src/index.ts
 * Version: 0.11.3 (commit b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Copied with the minimal deviations noted below. Do not otherwise edit.
 *
 * Deviation: `./transcript-buffer` is not vendored (STT-side, unused by Bright).
 */
export * from './eventa'
export * from './llm-streaming-control'
export * from './managers/playback-manager'
export * from './priority'
export * from './processors/tts-chunker'
export * from './speech-pipeline'
export * from './stream'
export * from './timeline'
export * from './types'
export * from './utils/error-message'
