/**
 * Vendored from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/pipelines-audio/src/eventa.ts
 * Version: 0.11.3 (commit b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Copied VERBATIM. Do not edit — re-vendor from upstream instead.
 */

import type {
  PlaybackEndEvent,
  PlaybackInterruptEvent,
  PlaybackRejectEvent,
  PlaybackStartEvent,
  TextSegment,
  TtsRequest,
  TtsResult,
} from './types'

import { defineEventa } from '@moeru/eventa'

export const speechSegmentEvent = defineEventa<TextSegment>('proj-airi:pipelines:output:speech:segment')
export const speechSpecialEvent = defineEventa<TextSegment>('proj-airi:pipelines:output:speech:special')

export const speechTtsRequestEvent = defineEventa<TtsRequest>('proj-airi:pipelines:output:speech:tts-request')
export const speechTtsResultEvent = defineEventa<TtsResult<unknown>>('proj-airi:pipelines:output:speech:tts-result')

export const speechPlaybackStartEvent = defineEventa<PlaybackStartEvent<unknown>>('proj-airi:pipelines:output:speech:playback-start')
export const speechPlaybackEndEvent = defineEventa<PlaybackEndEvent<unknown>>('proj-airi:pipelines:output:speech:playback-end')
export const speechPlaybackInterruptEvent = defineEventa<PlaybackInterruptEvent<unknown>>('proj-airi:pipelines:output:speech:playback-interrupt')
export const speechPlaybackRejectEvent = defineEventa<PlaybackRejectEvent<unknown>>('proj-airi:pipelines:output:speech:playback-reject')

export const speechIntentStartEvent = defineEventa<string>('proj-airi:pipelines:output:speech:intent-start')
export const speechIntentEndEvent = defineEventa<string>('proj-airi:pipelines:output:speech:intent-end')
export const speechIntentCancelEvent = defineEventa<{ intentId: string, reason?: string }>('proj-airi:pipelines:output:speech:intent-cancel')

export const speechTurnStartEvent = defineEventa<string>('proj-airi:pipelines:output:speech:turn-start')
export const speechTurnEndEvent = defineEventa<string>('proj-airi:pipelines:output:speech:turn-end')
export const speechTurnCancelEvent = defineEventa<{ turnId: string, reason?: string }>('proj-airi:pipelines:output:speech:turn-cancel')

export const speechPipelineEventMap = {
  onSegment: speechSegmentEvent,
  onSpecial: speechSpecialEvent,
  onTtsRequest: speechTtsRequestEvent,
  onTtsResult: speechTtsResultEvent,
  onPlaybackStart: speechPlaybackStartEvent,
  onPlaybackEnd: speechPlaybackEndEvent,
  onPlaybackInterrupt: speechPlaybackInterruptEvent,
  onPlaybackReject: speechPlaybackRejectEvent,
  onIntentStart: speechIntentStartEvent,
  onIntentEnd: speechIntentEndEvent,
  onIntentCancel: speechIntentCancelEvent,
  onTurnStart: speechTurnStartEvent,
  onTurnEnd: speechTurnEndEvent,
  onTurnCancel: speechTurnCancelEvent,
} as const

export type SpeechPipelineEventName = keyof typeof speechPipelineEventMap
