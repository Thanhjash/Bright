/** Cross-window half-duplex signal between the projector and control routes. */
const CHANNEL = 'bright-speech-output-v1'
const ECHO_TAIL_MS = 800

type Listener = () => void
type Message = {
  type: 'started' | 'playback-started' | 'finished'
  speechTurnId: string
  at: number
  status?: 'completed' | 'cancelled' | 'failed'
}

const listeners = new Set<Listener>()
const active = new Set<string>()
let playing: string | null = null
let suppressedUntil = 0
let channel: BroadcastChannel | null = null

function notify(): void {
  for (const listener of listeners)
    listener()
}

function apply(message: Message): void {
  if (message.type === 'started') {
    active.add(message.speechTurnId)
  }
  else if (message.type === 'playback-started') {
    active.add(message.speechTurnId)
    playing = message.speechTurnId
  }
  else {
    active.delete(message.speechTurnId)
    if (playing === message.speechTurnId) playing = null
    suppressedUntil = Math.max(suppressedUntil, message.at + ECHO_TAIL_MS)
    const remaining = Math.max(0, suppressedUntil - Date.now())
    setTimeout(notify, remaining + 1)
  }
  notify()
}

function bus(): BroadcastChannel | null {
  if (channel || typeof BroadcastChannel === 'undefined')
    return channel
  channel = new BroadcastChannel(CHANNEL)
  channel.addEventListener('message', (event: MessageEvent<Message>) => apply(event.data))
  return channel
}

export function publishOutputActivity(
  type: Message['type'],
  speechTurnId: string,
  status?: Message['status'],
): void {
  const message: Message = { type, speechTurnId, at: Date.now(), ...(status ? { status } : {}) }
  apply(message)
  bus()?.postMessage(message)
}

/** Apply a Core speech intent in this tab without echoing it to Stage. */
export function observeOutputActivity(type: Message['type'], speechTurnId: string): void {
  apply({ type, speechTurnId, at: Date.now() })
}

/** Snapshot of exact output turns observed from the Stage tab. */
export function activeSpeechTurnIds(): string[] {
  bus()
  return [...active]
}

/** Forget connection-scoped observations before applying a full snapshot. */
export function resetOutputActivity(): void {
  active.clear()
  playing = null
  suppressedUntil = 0
  notify()
}

/** Exact audible turn, falling back to the sole queued intent before audio starts. */
export function interruptibleSpeechTurnId(): string | null {
  bus()
  if (playing && active.has(playing)) return playing
  return active.size === 1 ? [...active][0] : null
}

/**
 * Wait for the exact Stage turn to become terminal and for the acoustic echo
 * tail to expire. Timeout is a rejection signal: callers must keep mic closed.
 */
export function waitForMicrophoneRelease(
  speechTurnId: string,
  timeoutMs = 2_500,
): Promise<boolean> {
  bus()
  return new Promise((resolve) => {
    let done = false
    const finish = (released: boolean) => {
      if (done) return
      done = true
      clearTimeout(timeout)
      unsubscribe()
      resolve(released)
    }
    const check = () => {
      if (!active.has(speechTurnId) && !isMicrophoneSuppressed()) finish(true)
    }
    const unsubscribe = subscribeOutputActivity(check)
    const timeout = setTimeout(() => finish(false), timeoutMs)
    check()
  })
}

export function isMicrophoneSuppressed(): boolean {
  bus()
  return active.size > 0 || Date.now() < suppressedUntil
}

export function subscribeOutputActivity(listener: Listener): () => void {
  bus()
  listeners.add(listener)
  return () => listeners.delete(listener)
}
