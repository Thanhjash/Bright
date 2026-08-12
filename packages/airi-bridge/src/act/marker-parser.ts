/**
 * ACT / DELAY token parser.
 *
 * Ported from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/core-agent/src/runtime/llm-marker-parser.ts (v0.11.3 @ b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Rewritten rather than vendored, for two reasons:
 *
 *  1. The upstream public entry point (`useLlmmarkerParser`) pushes deltas into an
 *     unbounded `ReadableStream` and returns immediately, so `consume()` gives the
 *     caller no back-pressure. PROTOCOL.md §5 requirement 3 says "await the parser on
 *     every delta". The scanning loop below is upstream's `createLlmMarkerParser`
 *     verbatim in behaviour — it awaits `onLiteral` / `onSpecial` inside `consume()` —
 *     and it is what this module exposes.
 *  2. `TAG_OPEN` / `TAG_CLOSE` / `TAG_TAIL_RETAIN` come from packages/contracts
 *     instead of being redeclared.
 *
 * THE INVARIANT THAT MATTERS (PROTOCOL.md §5 requirement 1):
 * when no `<|` has been seen, the scanner retains the last TAG_TAIL_RETAIN (5)
 * characters instead of emitting them, because a token opener split across two SSE
 * chunks must never leak into spoken text. 5 is `ESCAPED_TAG_OPEN.length - 1` — the
 * longest opener the parser recognises is the 6-character escaped form `<{'|'}`, so
 * five retained characters are exactly enough to never emit a partial opener.
 * Do not lower it.
 */

import { TAG_CLOSE, TAG_OPEN, TAG_TAIL_RETAIN } from '../contracts'

/**
 * Models sometimes escape the marker syntax so it can be talked about without
 * triggering it. Unescape before scanning, exactly as upstream does.
 */
const ESCAPED_TAG_OPEN = '<{\'|\'}'
const ESCAPED_TAG_CLOSE = '{\'|\'}>'

/* The retained tail only works if it covers the longest opener we recognise. */
const REQUIRED_TAIL = Math.max(TAG_OPEN.length - 1, ESCAPED_TAG_OPEN.length - 1)
if (TAG_TAIL_RETAIN < REQUIRED_TAIL) {
  throw new Error(
    `[airi-bridge/act] TAG_TAIL_RETAIN is ${TAG_TAIL_RETAIN} but the longest recognised `
    + `token opener needs ${REQUIRED_TAIL}. A token split across two chunks would leak as `
    + `spoken text. Fix packages/contracts, not this file.`,
  )
}

/** Plain text that should be spoken. */
export interface MarkerLiteralEvent {
  type: 'literal'
  text: string
}

/** A complete `<|...|>` token, delimiters included. Never spoken. */
export interface MarkerSpecialEvent {
  type: 'special'
  raw: string
}

export type MarkerEvent = MarkerLiteralEvent | MarkerSpecialEvent

export interface MarkerParserOptions {
  /**
   * Minimum literal length to emit while no token opener is in sight. Raising it
   * batches downstream work at the cost of latency.
   *
   * @default 1
   */
  minLiteralEmitLength?: number
}

export interface MarkerParser {
  /**
   * Feeds one stream delta. Resolves only after every event it produced has been
   * handled — this is the back-pressure PROTOCOL.md §5 requires. Always `await` it.
   */
  consume: (textPart: string) => Promise<void>
  /**
   * Ends the stream. Flushes the retained tail as literal text.
   *
   * An unterminated token (an opener with no `|>`) is DROPPED here, never emitted
   * as text — a half-written token must not be spoken.
   */
  end: () => Promise<void>
  /** Discards buffered state. Use when a turn is cancelled mid-stream. */
  reset: () => void
  /** True while an opener has been seen and its `|>` has not. */
  isInToken: () => boolean
}

/**
 * Creates a streaming parser that separates spoken text from `<|...|>` control tokens.
 *
 * @example
 * const parser = createMarkerParser(async (event) => {
 *   if (event.type === 'literal') await speak(event.text)
 *   else await dispatch(parseAct(event.raw))
 * })
 * for await (const delta of sse) await parser.consume(delta)
 * await parser.end()
 */
export function createMarkerParser(
  onEvent: (event: MarkerEvent) => void | Promise<void>,
  options?: MarkerParserOptions,
): MarkerParser {
  const minLiteralEmitLength = Math.max(1, options?.minLiteralEmitLength ?? 1)
  const tailLength = TAG_TAIL_RETAIN

  let buffer = ''
  let inTag = false

  async function emitLiteral(text: string) {
    if (!text)
      return
    await onEvent({ type: 'literal', text })
  }

  async function emitSpecial(raw: string) {
    await onEvent({ type: 'special', raw })
  }

  return {
    async consume(textPart: string) {
      buffer += textPart
      buffer = buffer
        .replaceAll(ESCAPED_TAG_OPEN, TAG_OPEN)
        .replaceAll(ESCAPED_TAG_CLOSE, TAG_CLOSE)

      while (buffer.length > 0) {
        if (!inTag) {
          const openTagIndex = buffer.indexOf(TAG_OPEN)
          if (openTagIndex < 0) {
            // No opener in sight. Emit everything except the retained tail, which
            // may yet turn out to be the first half of an opener.
            if (buffer.length - tailLength >= minLiteralEmitLength) {
              const emit = buffer.slice(0, -tailLength)
              buffer = buffer.slice(-tailLength)
              await emitLiteral(emit)
            }
            break
          }

          if (openTagIndex > 0) {
            const emit = buffer.slice(0, openTagIndex)
            buffer = buffer.slice(openTagIndex)
            await emitLiteral(emit)
          }
          inTag = true
        }
        else {
          const closeTagIndex = buffer.indexOf(TAG_CLOSE)
          // Closer not here yet: hold the whole partial token, emit nothing.
          if (closeTagIndex < 0)
            break

          const emit = buffer.slice(0, closeTagIndex + TAG_CLOSE.length)
          buffer = buffer.slice(closeTagIndex + TAG_CLOSE.length)
          await emitSpecial(emit)
          inTag = false
        }
      }
    },

    async end() {
      // `inTag` here means the stream ended inside a token. Drop it.
      if (!inTag && buffer.length > 0)
        await emitLiteral(buffer)

      buffer = ''
      inTag = false
    },

    reset() {
      buffer = ''
      inTag = false
    },

    isInToken() {
      return inTag
    },
  }
}

/**
 * Convenience wrapper for callers that would rather have two callbacks than an
 * event union. Same back-pressure guarantees.
 */
export function createMarkerParserWithHandlers(handlers: {
  onLiteral?: (text: string) => void | Promise<void>
  onSpecial?: (raw: string) => void | Promise<void>
  minLiteralEmitLength?: number
}): MarkerParser {
  return createMarkerParser(
    async (event) => {
      if (event.type === 'literal')
        await handlers.onLiteral?.(event.text)
      else
        await handlers.onSpecial?.(event.raw)
    },
    { minLiteralEmitLength: handlers.minLiteralEmitLength },
  )
}

/**
 * Non-streaming helper: splits a complete string into ordered marker events.
 * Handy in tests and for pre-rendered narration text.
 */
export async function parseMarkerText(text: string): Promise<MarkerEvent[]> {
  const events: MarkerEvent[] = []
  const parser = createMarkerParser(event => void events.push(event))
  await parser.consume(text)
  await parser.end()
  return events
}
