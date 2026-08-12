/** Ephemeral same-appliance cue from Control's mic owner to the Stage window. */
const CHANNEL = 'bright-answer-station-v1'

export type AnswerStationPhase = 'assigned' | 'opening' | 'listening' | 'thinking' | 'waiting' | 'error' | 'idle'
export interface AnswerStationActivity {
  assignmentId?: string
  captureId?: string
  phase: AnswerStationPhase
  at: number
}

type WireMessage =
  | { type: 'activity'; activity: AnswerStationActivity }
  | { type: 'query' }

let current: AnswerStationActivity = { phase: 'idle', at: Date.now() }
let channel: BroadcastChannel | null = null
// Only the page that actually owns useVoiceInput is authoritative. A Stage
// may cache received activity, but must not answer another Stage's query with
// that possibly stale cache.
let publisher = false
const listeners = new Set<(activity: AnswerStationActivity) => void>()

function ensureChannel(): BroadcastChannel | null {
  if (channel || typeof BroadcastChannel === 'undefined') return channel
  channel = new BroadcastChannel(CHANNEL)
  channel.addEventListener('message', ({ data }: MessageEvent<WireMessage>) => {
    if (data.type === 'query') {
      if (!publisher) return
      channel?.postMessage({ type: 'activity', activity: current } satisfies WireMessage)
      return
    }
    current = data.activity
    for (const listener of listeners) listener(current)
  })
  return channel
}

export function publishAnswerStationActivity(activity: Omit<AnswerStationActivity, 'at'>): void {
  publisher = true
  current = { ...activity, at: Date.now() }
  for (const listener of listeners) listener(current)
  ensureChannel()?.postMessage({ type: 'activity', activity: current } satisfies WireMessage)
}

export function subscribeAnswerStationActivity(
  listener: (activity: AnswerStationActivity) => void,
): () => void {
  listeners.add(listener)
  listener(current)
  ensureChannel()?.postMessage({ type: 'query' } satisfies WireMessage)
  return () => listeners.delete(listener)
}
