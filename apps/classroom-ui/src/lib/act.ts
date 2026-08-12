/**
 * Display-only ACT-token scrubber — PROTOCOL.md §5.
 *
 * The real, back-pressured, tail-retaining stream parser belongs to
 * packages/airi-bridge; it sits between the agent stream and the audio
 * pipeline. This is a defensive net for one narrow case: a `speech.say`
 * payload whose `text` still contains `<|ACT …|>` / `<|DELAY …|>`. Those must
 * never appear in a subtitle projected in front of a class. If the token is
 * a well-formed ACT we also lift the emotion out, so the placeholder avatar
 * reacts even before airi-bridge lands.
 *
 * It operates on whole payloads, not stream chunks — so it needs no tail
 * retention. Do not grow this into a stream parser; use airi-bridge.
 */
import { EMOTIONS, TAG_CLOSE, TAG_OPEN } from '@contracts'
import type { ActPayload, Emotion } from '@contracts'

const EMOTION_SET = new Set<string>(EMOTIONS)

export function isEmotion(value: unknown): value is Emotion {
  return typeof value === 'string' && EMOTION_SET.has(value)
}

/** Emotion name out of the two accepted `ActPayload.emotion` shapes. */
export function emotionName(act: ActPayload | undefined): Emotion | undefined {
  const e = act?.emotion
  if (!e) return undefined
  if (typeof e === 'string') return isEmotion(e) ? e : undefined
  return isEmotion(e.name) ? e.name : undefined
}

export function emotionIntensity(act: ActPayload | undefined): number {
  const e = act?.emotion
  if (!e || typeof e === 'string') return 1
  const i = e.intensity
  return typeof i === 'number' && i >= 0 && i <= 1 ? i : 1
}

export interface ScrubbedText {
  /** The text with every `<|…|>` token removed, safe to project. */
  text: string
  /** ACT payloads found, in order. */
  acts: ActPayload[]
}

export function scrubActTokens(raw: string): ScrubbedText {
  if (!raw.includes(TAG_OPEN)) return { text: raw, acts: [] }

  const acts: ActPayload[] = []
  let out = ''
  let i = 0

  while (i < raw.length) {
    const open = raw.indexOf(TAG_OPEN, i)
    if (open === -1) {
      out += raw.slice(i)
      break
    }
    out += raw.slice(i, open)
    const close = raw.indexOf(TAG_CLOSE, open + TAG_OPEN.length)
    if (close === -1) {
      // Unterminated token: dropped, never emitted as text.
      break
    }
    const body = raw.slice(open + TAG_OPEN.length, close).trim()
    if (body.startsWith('ACT')) {
      const act = parseAct(body.slice(3).trim())
      if (act) acts.push(act)
    }
    // `DELAY n` and anything unrecognised are simply removed.
    i = close + TAG_CLOSE.length
  }

  return { text: out.replace(/\s{2,}/g, ' ').trim(), acts }
}

function parseAct(json: string): ActPayload | null {
  try {
    const raw: unknown = JSON.parse(json)
    if (!raw || typeof raw !== 'object') return null
    const obj = raw as Record<string, unknown>
    const act: ActPayload = {}

    const e = obj.emotion
    if (isEmotion(e)) {
      act.emotion = e
    } else if (e && typeof e === 'object') {
      const { name, intensity } = e as Record<string, unknown>
      if (isEmotion(name)) {
        act.emotion = {
          name,
          intensity: typeof intensity === 'number' ? Math.min(1, Math.max(0, intensity)) : 1,
        }
      }
    }
    if (typeof obj.motion === 'string') act.motion = obj.motion

    return act.emotion || act.motion ? act : null
  } catch {
    return null
  }
}
