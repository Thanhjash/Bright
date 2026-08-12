/**
 * Per-model binding — the `bright-model.json` file that ships next to a Live2D model.
 *
 * WHY THIS EXISTS. `EMOTION_MOTION_GROUP` in packages/contracts maps each of the nine
 * emotions to a capitalised motion group name (`happy` → `Happy`, `neutral` → `Idle`).
 * That is the right default and it stays the default. But real models mostly do not
 * ship per-emotion motion groups: the Haru sample has motion groups `Idle` and `Tap`
 * and nothing else, so every emotion would miss and the avatar would sit still while
 * appearing to work. Models like that express emotion through EXPRESSIONS
 * (`.exp3.json` parameter overlays), which are per-model and arbitrarily named.
 *
 * So emotion dispatch is config-driven. No expression id and no motion group name is
 * ever hard-coded in this package. A model directory supplies `bright-model.json`;
 * a model without one falls back to the contract table.
 *
 * Nothing in this file throws on bad input. A malformed binding degrades to the
 * contract default rather than taking the classroom down.
 */

import type { Emotion } from '../contracts'

import { EMOTION_MOTION_GROUP, EMOTIONS } from '../contracts'

/** Which mechanism this model uses to show emotion. */
export type EmotionChannel = 'expression' | 'motion'

/**
 * How one emotion is realised on one model.
 *
 * `expression: null` is meaningful and distinct from `expression: undefined` — it
 * means "clear any active expression", which is how a model returns to neutral.
 */
export interface EmotionBinding {
  /** Expression reference: its `Name` in model3.json, its file basename, or its index. */
  expression?: string | number | null
  /** Motion group to play. Overrides the contract default for this emotion. */
  motion?: string | null
  /** Author's confidence in the mapping. Advisory; not used at runtime. */
  confidence?: 'high' | 'medium' | 'low'
  /** Why the author chose this. Advisory; not used at runtime. */
  why?: string
}

export interface MotionGroupBinding {
  /** Groups the model actually ships. Empty means "unknown, try anyway". */
  available: string[]
  /** The looping idle group. */
  idle: string
  /** Last resort before giving up on an emotion. */
  fallback: string
}

export interface LipSyncBinding {
  /**
   * Cubism parameter the mouth-open value is written to.
   *
   * PROTOCOL.md §6.5: `getMouthOpen()` returns 0…0.7 and is written RAW to this
   * parameter, which expects 0…1. Do NOT rescale.
   */
  parameter: string
  range: [number, number]
}

export interface LayoutBinding {
  anchor: 'center' | 'bottom-left' | 'bottom-right' | 'bottom-center'
  /** Multiplier on the fit-to-viewport scale. */
  scale: number
  /** Fraction of canvas width / height. */
  offsetX: number
  offsetY: number
}

export interface Live2DModelBinding {
  id: string
  name?: string
  /** Model entry file, relative to the binding file. */
  modelPath: string
  /** Cubism core runtime script, relative to the binding file. Not npm-installable. */
  cubismCore?: string
  cubismVersion?: number
  emotionChannel: EmotionChannel
  emotionMap: Partial<Record<Emotion, EmotionBinding>>
  motionGroups: MotionGroupBinding
  lipSync: LipSyncBinding
  layout: LayoutBinding
  /** Free-form licence block. Carried through so a build step can assert on it. */
  license?: Record<string, unknown>
}

/**
 * The binding used when a model ships none: the contract table, motion channel.
 *
 * PROTOCOL.md §5 — the motion group is the capitalised emotion name, except
 * `neutral` → `Idle`.
 */
export const DEFAULT_MODEL_BINDING: Omit<Live2DModelBinding, 'id' | 'modelPath'> = {
  emotionChannel: 'motion',
  emotionMap: Object.fromEntries(
    EMOTIONS.map(emotion => [emotion, { motion: EMOTION_MOTION_GROUP[emotion] }]),
  ) as Record<Emotion, EmotionBinding>,
  motionGroups: { available: [], idle: 'Idle', fallback: 'Idle' },
  lipSync: { parameter: 'ParamMouthOpenY', range: [0, 1] },
  layout: { anchor: 'center', scale: 1, offsetX: 0, offsetY: 0 },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asString(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((x): x is string => typeof x === 'string') : []
}

function parseEmotionBinding(value: unknown): EmotionBinding | undefined {
  if (!isRecord(value))
    return undefined

  const binding: EmotionBinding = {}

  // `null` survives; `undefined` (absent key) does not. The difference decides
  // whether neutral clears the active expression or leaves it alone.
  if ('expression' in value) {
    const expression = value.expression
    if (expression === null || typeof expression === 'string' || typeof expression === 'number')
      binding.expression = expression
  }
  if ('motion' in value) {
    const motion = value.motion
    if (motion === null || typeof motion === 'string')
      binding.motion = motion
  }
  if (typeof value.confidence === 'string')
    binding.confidence = value.confidence as EmotionBinding['confidence']
  if (typeof value.why === 'string')
    binding.why = value.why

  return binding
}

/**
 * Parses a `bright-model.json` document.
 *
 * Tolerant by design: `$comment*` keys are ignored, unknown emotions are dropped,
 * missing sections fall back to `DEFAULT_MODEL_BINDING`, and nothing throws. A
 * binding file is authored by hand and read in front of a class; a typo must
 * degrade, not crash.
 *
 * @param document parsed JSON, or anything at all
 * @param fallbackId used when the document has no `id`
 */
export function parseModelBinding(document: unknown, fallbackId = 'unknown'): Live2DModelBinding {
  if (!isRecord(document)) {
    return {
      ...DEFAULT_MODEL_BINDING,
      id: fallbackId,
      modelPath: '',
    }
  }

  const rawMap = isRecord(document.emotionMap) ? document.emotionMap : {}
  const emotionMap: Partial<Record<Emotion, EmotionBinding>> = {}
  for (const emotion of EMOTIONS) {
    const parsed = parseEmotionBinding(rawMap[emotion])
    if (parsed)
      emotionMap[emotion] = parsed
  }

  const rawGroups = isRecord(document.motionGroups) ? document.motionGroups : {}
  const rawLipSync = isRecord(document.lipSync) ? document.lipSync : {}
  const rawLayout = isRecord(document.layout) ? document.layout : {}

  const channel = document.emotionChannel === 'expression' ? 'expression' : 'motion'
  const idle = asString(rawGroups.idle, DEFAULT_MODEL_BINDING.motionGroups.idle)
  const range = Array.isArray(rawLipSync.range) && rawLipSync.range.length === 2
    ? [asNumber(rawLipSync.range[0], 0), asNumber(rawLipSync.range[1], 1)] as [number, number]
    : DEFAULT_MODEL_BINDING.lipSync.range

  return {
    id: asString(document.id, fallbackId),
    name: typeof document.name === 'string' ? document.name : undefined,
    modelPath: asString(document.modelPath, ''),
    cubismCore: typeof document.cubismCore === 'string' ? document.cubismCore : undefined,
    cubismVersion: asNumber(document.cubismVersion, 4),
    emotionChannel: channel,
    // An `expression` channel with an empty map would silently do nothing on every
    // emotion, so fall back to the contract table rather than to no behaviour at all.
    emotionMap: Object.keys(emotionMap).length > 0 ? emotionMap : DEFAULT_MODEL_BINDING.emotionMap,
    motionGroups: {
      available: asStringArray(rawGroups.available),
      idle,
      fallback: asString(rawGroups.fallback, idle),
    },
    lipSync: {
      parameter: asString(rawLipSync.parameter, DEFAULT_MODEL_BINDING.lipSync.parameter),
      range,
    },
    layout: {
      anchor: asString(rawLayout.anchor, 'center') as LayoutBinding['anchor'],
      scale: asNumber(rawLayout.scale, 1),
      offsetX: asNumber(rawLayout.offsetX, 0),
      offsetY: asNumber(rawLayout.offsetY, 0),
    },
    license: isRecord(document.license) ? document.license : undefined,
  }
}

/**
 * Fetches and parses a binding file, resolving `modelPath` and `cubismCore`
 * against the binding's own URL.
 *
 * Returns the contract default if the file is missing or unreadable — a model
 * without a binding is a supported case, not an error.
 */
export async function loadModelBinding(
  bindingUrl: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Live2DModelBinding & { modelUrl: string, cubismCoreUrl?: string }> {
  let document: unknown
  try {
    const response = await fetchImpl(bindingUrl)
    if (!response.ok)
      throw new Error(`HTTP ${response.status}`)
    document = await response.json()
  }
  catch (error) {
    console.warn(`[airi-bridge] no usable binding at ${bindingUrl}; using the contract default.`, error)
    document = undefined
  }

  const binding = parseModelBinding(document, bindingUrl)
  const resolve = (path: string) => new URL(path, new URL(bindingUrl, globalThis.location?.href ?? 'http://localhost/')).toString()

  return {
    ...binding,
    modelUrl: binding.modelPath ? resolve(binding.modelPath) : '',
    cubismCoreUrl: binding.cubismCore ? resolve(binding.cubismCore) : undefined,
  }
}
