/**
 * Emotion → model action, with a fallback chain that never dead-ends.
 *
 * The chain, in order:
 *
 *   1. the binding's configured EXPRESSION for this emotion, if the model has it
 *   2. the binding's configured MOTION GROUP for this emotion, if the model has it
 *   3. the contract default motion group (`EMOTION_MOTION_GROUP`), if the model has it
 *   4. `motionGroups.fallback` (normally `Idle`), if the model has it
 *   5. nothing — return `{ kind: 'none' }`
 *
 * Step 1 is skipped when `emotionChannel` is `'motion'`; step 2 is still consulted
 * either way, so a mostly-expression model can pin one emotion to a motion group.
 *
 * This function is pure and never throws. Unmapped emotions are reported through the
 * returned `source`, and `createEmotionResolver` logs each distinct miss ONCE — an
 * emotion that misses will miss on every single turn, and a warning per frame in
 * front of a class is worse than the miss.
 */

import type { Emotion } from '../contracts'
import type { ExpressionIndex } from './expression-index'
import type { Live2DModelBinding } from './model-binding'

import { EMOTION_MOTION_GROUP } from '../contracts'
import { resolveExpressionRef } from './expression-index'

/** What the stage should actually do. */
export type EmotionAction
  = /** Apply this expression. `index` is what pixi-live2d-display wants. */
  | { kind: 'expression', index: number, id: string }
  /** Remove any active expression. How a model returns to neutral. */
  | { kind: 'clear-expression' }
  /** Play this motion group. */
  | { kind: 'motion', group: string }
  /** Model can express this emotion no way at all. Leave it alone. */
  | { kind: 'none' }

export type EmotionActionSource
  = | 'binding-expression'
    | 'binding-clear-expression'
    | 'binding-motion'
    | 'contract-motion'
    | 'fallback-motion'
    | 'unmapped'

export interface EmotionResolution {
  emotion: Emotion
  action: EmotionAction
  source: EmotionActionSource
}

/** What the loaded model can actually do. Discovered after load, never assumed. */
export interface ModelCapabilities {
  expressions: ExpressionIndex
  /** Motion group names the model ships. */
  motionGroups: string[]
}

export const EMPTY_CAPABILITIES: ModelCapabilities = {
  expressions: [],
  motionGroups: [],
}

/**
 * Whether the model has this motion group.
 *
 * A binding whose `motionGroups.available` is empty means "not declared" — in that
 * case trust the model's own group list. If BOTH are empty we have no information,
 * so allow the group through and let pixi-live2d-display no-op on it; refusing would
 * turn "we didn't look" into "it doesn't exist".
 */
function hasMotionGroup(group: string, binding: Live2DModelBinding, capabilities: ModelCapabilities): boolean {
  const declared = binding.motionGroups.available
  const discovered = capabilities.motionGroups

  if (discovered.length > 0)
    return discovered.includes(group)
  if (declared.length > 0)
    return declared.includes(group)
  return true
}

/**
 * Resolves one emotion into one model action.
 *
 * @example
 * // Haru: no per-emotion motion groups, so 'happy' lands on expression F05
 * resolveEmotionAction('happy', haruBinding, haruCapabilities)
 * // => { emotion: 'happy', action: { kind: 'expression', index: 4, id: 'F05' }, source: 'binding-expression' }
 */
export function resolveEmotionAction(
  emotion: Emotion,
  binding: Live2DModelBinding,
  capabilities: ModelCapabilities = EMPTY_CAPABILITIES,
): EmotionResolution {
  const entry = binding.emotionMap[emotion]

  // 1. configured expression
  if (binding.emotionChannel === 'expression' && entry && 'expression' in entry) {
    if (entry.expression === null)
      return { emotion, action: { kind: 'clear-expression' }, source: 'binding-clear-expression' }

    if (entry.expression !== undefined) {
      const resolved = resolveExpressionRef(capabilities.expressions, entry.expression)
      if (resolved) {
        return {
          emotion,
          action: { kind: 'expression', index: resolved.index, id: resolved.id },
          source: 'binding-expression',
        }
      }
    }
  }

  // 2. configured motion group
  if (entry?.motion && hasMotionGroup(entry.motion, binding, capabilities))
    return { emotion, action: { kind: 'motion', group: entry.motion }, source: 'binding-motion' }

  // 3. contract default motion group
  const contractGroup = EMOTION_MOTION_GROUP[emotion]
  if (contractGroup && hasMotionGroup(contractGroup, binding, capabilities))
    return { emotion, action: { kind: 'motion', group: contractGroup }, source: 'contract-motion' }

  // 4. last-resort fallback group
  const fallback = binding.motionGroups.fallback
  if (fallback && hasMotionGroup(fallback, binding, capabilities))
    return { emotion, action: { kind: 'motion', group: fallback }, source: 'fallback-motion' }

  // 5. give up quietly
  return { emotion, action: { kind: 'none' }, source: 'unmapped' }
}

export interface EmotionResolver {
  resolve: (emotion: Emotion) => EmotionResolution
  /** Emotions that fell through to the fallback or to nothing, in first-seen order. */
  degradedEmotions: () => Emotion[]
}

/**
 * Wraps `resolveEmotionAction` with once-per-emotion logging.
 *
 * Create one per loaded model. Re-creating it re-arms the warnings, which is what
 * you want when the model changes.
 */
export function createEmotionResolver(
  binding: Live2DModelBinding,
  capabilities: ModelCapabilities = EMPTY_CAPABILITIES,
  logger: Pick<Console, 'warn'> = console,
): EmotionResolver {
  const warned = new Set<Emotion>()
  const degraded: Emotion[] = []

  return {
    resolve(emotion) {
      const resolution = resolveEmotionAction(emotion, binding, capabilities)

      if (resolution.source === 'fallback-motion' || resolution.source === 'unmapped') {
        if (!warned.has(emotion)) {
          warned.add(emotion)
          degraded.push(emotion)
          logger.warn(
            `[airi-bridge] model "${binding.id}" cannot express "${emotion}" `
            + `(${resolution.source}). Add it to emotionMap in bright-model.json. `
            + `This is logged once per emotion.`,
          )
        }
      }

      return resolution
    },
    degradedEmotions: () => [...degraded],
  }
}
