/**
 * Token payload decoding: `<|ACT {...}|>` and `<|DELAY 1.5|>` → typed contract values.
 *
 * The token matchers and the normaliser come from the vendored AIRI code
 * (`src/vendor/pipelines-audio/llm-streaming-control/`). This module is the thin
 * layer that turns them into `ActPayload` from packages/contracts, which is the
 * only emotion/motion shape the rest of Bright is allowed to speak.
 *
 * PROTOCOL.md §5:
 *  - `emotion` accepts a bare string OR `{ name, intensity }`.
 *  - `intensity` is clamped to [0,1]; a numeric STRING is accepted (streamed
 *    payloads frequently arrive serialised); anything unparseable falls back to 1.
 *  - An emotion outside the nine in `EMOTIONS` yields `emotion: undefined` —
 *    `motion` on the same token is still honoured.
 *  - DELAY is SPACE separated. `<|DELAY:1.5|>` is not a DELAY token.
 */

import type { ActPayload, Emotion } from '../contracts'

import { tokenAct, tokenDelay } from '../vendor/pipelines-audio/llm-streaming-control/parsers'
import { normalizeActPayload } from '../vendor/pipelines-audio/llm-streaming-control/payloads'

const actParser = tokenAct()
const delayParser = tokenDelay()

/** Emotion with its strength. `intensity` is always present and always in [0,1]. */
export interface ResolvedEmotion {
  name: Emotion
  intensity: number
}

/** True when `raw` is syntactically a `<|ACT ...|>` token (payload may still be junk). */
export function isActToken(raw: string): boolean {
  return actParser.match(raw)
}

/** True when `raw` is syntactically a `<|DELAY ...|>` token. */
export function isDelayToken(raw: string): boolean {
  return delayParser.match(raw)
}

/**
 * Decodes a raw `<|ACT {...}|>` token into an `ActPayload`.
 *
 * Returns `undefined` when `raw` is not an ACT token or its body is not a JSON
 * object. Returns an object (possibly empty) otherwise — an ACT whose emotion is
 * unrecognised is still a valid ACT, it just carries no emotion.
 *
 * @example
 * parseAct('<|ACT {"emotion":"happy"}|>')
 * // => { emotion: { name: 'happy', intensity: 1 } }
 * parseAct('<|ACT {"emotion":{"name":"think","intensity":"0.6"}}|>')
 * // => { emotion: { name: 'think', intensity: 0.6 } }
 * parseAct('<|ACT {"emotion":"sleepy","motion":"nod"}|>')
 * // => { motion: 'nod' }
 */
export function parseAct(raw: string): ActPayload | undefined {
  if (!actParser.match(raw))
    return undefined

  const parsed = actParser.parse(raw)
  if (!parsed)
    return undefined

  const normalized = normalizeActPayload(parsed.payload)

  const act: ActPayload = {}
  if (normalized.emotion)
    act.emotion = { name: normalized.emotion.name, intensity: normalized.emotion.intensity }
  if (normalized.motion)
    act.motion = normalized.motion

  return act
}

/**
 * Decodes a raw `<|DELAY 1.5|>` token into seconds.
 *
 * Returns `undefined` for a non-DELAY token, a non-positive value, or a
 * colon-separated payload (`<|DELAY:1.5|>` — a common but wrong spelling).
 */
export function parseDelay(raw: string): number | undefined {
  if (!delayParser.match(raw))
    return undefined
  return delayParser.parse(raw)?.seconds
}

/**
 * Normalises whatever shape an `ActPayload.emotion` arrived in — bare string or
 * `{ name, intensity }` — into a single shape with a guaranteed intensity.
 *
 * Use this instead of branching on the union at every call site. Returns
 * `undefined` when the payload carries no usable emotion.
 */
export function resolveEmotion(act: ActPayload | undefined): ResolvedEmotion | undefined {
  const emotion = act?.emotion
  if (!emotion)
    return undefined
  if (typeof emotion === 'string')
    return { name: emotion, intensity: 1 }
  return {
    name: emotion.name,
    intensity: Number.isFinite(emotion.intensity)
      ? Math.max(0, Math.min(1, emotion.intensity))
      : 1,
  }
}

/**
 * Decodes any special token into a discriminated signal.
 *
 * `kind: 'unknown'` covers tokens this build does not implement (`<|CALL ...|>`,
 * future syntaxes) and malformed ones. Callers should ignore those rather than
 * speak them — a token never becomes text.
 */
export type ActSignal
  = | { kind: 'act', act: ActPayload, raw: string }
    | { kind: 'delay', seconds: number, raw: string }
    | { kind: 'unknown', raw: string }

export function parseSignal(raw: string): ActSignal {
  const act = parseAct(raw)
  if (act)
    return { kind: 'act', act, raw }

  const seconds = parseDelay(raw)
  if (seconds !== undefined)
    return { kind: 'delay', seconds, raw }

  return { kind: 'unknown', raw }
}
