/**
 * Vendored from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/pipelines-audio/src/llm-streaming-control/parsers/act.ts
 * Version: 0.11.3 (commit b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Copied VERBATIM. Do not edit — re-vendor from upstream instead.
 */

import type { LlmStreamingControlParser, LlmStreamingControlTokenAct } from '../types'

const actTokenPrefix = '<|ACT '
const markerSuffix = '|>'

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Creates the parser for `<|ACT {...}|>` streaming-control tokens.
 *
 * Use when:
 * - Loading the built-in performance action control
 *
 * Expects:
 * - The token body is a JSON object literal
 *
 * Returns:
 * - Parsed action data with no side effects
 */
export function tokenAct(): LlmStreamingControlParser<LlmStreamingControlTokenAct> {
  return {
    name: 'ACT',
    match(special) {
      const trimmed = special.trim()
      return trimmed.startsWith(actTokenPrefix) && trimmed.endsWith(markerSuffix)
    },
    parse(special) {
      const trimmed = special.trim()
      const rawPayload = trimmed.slice(actTokenPrefix.length, -markerSuffix.length).trim()

      let parsed: unknown
      try {
        parsed = JSON.parse(rawPayload)
      }
      catch {
        return undefined
      }

      if (!isPlainObject(parsed)) {
        return undefined
      }

      return {
        type: 'act',
        payload: parsed,
      }
    },
  }
}
