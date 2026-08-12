/**
 * Vendored from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/pipelines-audio/src/llm-streaming-control/parsers/delay.ts
 * Version: 0.11.3 (commit b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Copied VERBATIM. Do not edit — re-vendor from upstream instead.
 *
 * Verbatim. Note the DELAY payload is SPACE separated (`<|DELAY 1.5|>`), never colon
 * separated. PROTOCOL.md §5.
 */

import type { LlmStreamingControlParser, LlmStreamingControlTokenDelay } from '../types'

const delayTokenPrefix = '<|DELAY '
const markerSuffix = '|>'

/**
 * Creates the parser for `<|DELAY n|>` streaming-control tokens.
 *
 * Use when:
 * - Loading the built-in performance delay control
 *
 * Expects:
 * - The token body is a finite positive number literal in seconds
 *
 * Returns:
 * - Parsed delay data with no side effects
 */
export function tokenDelay(): LlmStreamingControlParser<LlmStreamingControlTokenDelay> {
  return {
    name: 'DELAY',
    match(special) {
      const trimmed = special.trim()
      return trimmed.startsWith(delayTokenPrefix) && trimmed.endsWith(markerSuffix)
    },
    parse(special) {
      const trimmed = special.trim()
      const rawPayload = trimmed.slice(delayTokenPrefix.length, -markerSuffix.length).trim()
      if (!/^\d+(?:\.\d+)?$/.test(rawPayload)) {
        return undefined
      }

      const seconds = Number.parseFloat(rawPayload)
      if (!Number.isFinite(seconds) || seconds <= 0) {
        return undefined
      }

      return {
        type: 'delay',
        seconds,
      }
    },
  }
}
