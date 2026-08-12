/**
 * The §9.8 liveness readout — the one number that warns a teacher *before*
 * the room notices.
 *
 * "A link at 400 ms is still working; a link at 4 s is about to fail, and a
 * teacher deserves that warning before the room notices." So this shows two
 * things and no jargon:
 *
 *   · **Link** — `Date.now() - heartbeat.ts`. On the shipped appliance the two
 *     processes share a machine and therefore a clock, so this is honest
 *     server→client transit. Across unsynced machines it carries a constant
 *     offset, which is why the beat age sits beside it: the age is measured
 *     entirely on this clock and cannot be skewed.
 *   · **Beat age** — how long since the last heartbeat. The server sends every
 *     5 s, so anything past ~6 s is already wrong, and at 12 s the client
 *     declares the link dead and reconnects on its own.
 *
 * It re-renders once a second on its own, because "last beat 1 s ago" frozen
 * at 1 s while the link is actually dead is precisely the lie §9.8 exists to
 * stop telling.
 */
import { useEffect, useState } from 'react'
import { useClassroom } from '../../store/classroom'

/** Above this the link is worth a warning; above the second, a red one. */
const WARN_MS = 500
const BAD_MS = 2_000
/** The server's cadence (§9.8). One missed beat is already interesting. */
const BEAT_MS = 5_000

export function LinkHealth() {
  const state = useClassroom((s) => s.connection.state)
  const latency = useClassroom((s) => s.connection.latencyMs)
  const lastBeat = useClassroom((s) => s.connection.lastHeartbeatAt)

  // Own ticker: nothing else re-renders this while the link is silent, which
  // is exactly when it must keep counting.
  const [, tick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(t)
  }, [])

  if (state !== 'open' && state !== 'mock') {
    return <Pill tone="dead" label="No link" detail="waiting to reconnect" />
  }

  if (!lastBeat) {
    return (
      <Pill
        tone="warn"
        label="No heartbeat"
        detail="core has not sent one yet"
        title="PROTOCOL.md §9.8: classroom-core sends `heartbeat` every 5 s. Nothing has arrived on this connection; the board will declare the link dead after 12 s of silence."
      />
    )
  }

  const ageMs = Date.now() - lastBeat
  const tone: Tone =
    ageMs > BEAT_MS * 2 || (latency ?? 0) > BAD_MS
      ? 'dead'
      : ageMs > BEAT_MS * 1.4 || (latency ?? 0) > WARN_MS
        ? 'warn'
        : 'good'

  return (
    <Pill
      tone={tone}
      label={latency === null ? 'Link' : `Link ${fmt(latency)}`}
      detail={`beat ${fmt(ageMs)} ago`}
      title={`Heartbeat round trip ${latency ?? '—'} ms; last beat ${Math.round(ageMs / 100) / 10}s ago. No frame for 12 s and this board reconnects itself (PROTOCOL.md §9.8).`}
    />
  )
}

type Tone = 'good' | 'warn' | 'dead'

const TONE: Record<Tone, { dot: string; text: string }> = {
  good: { dot: 'bg-mint', text: 'text-mint' },
  warn: { dot: 'bg-amber', text: 'text-amber' },
  dead: { dot: 'bg-coral', text: 'text-coral' },
}

function Pill({
  tone,
  label,
  detail,
  title,
}: {
  tone: Tone
  label: string
  detail: string
  title?: string
}) {
  const look = TONE[tone]
  return (
    <span
      className="flex items-center gap-2.5 rounded-full bg-ink-800 px-4 py-2 text-sm font-bold ring-2 ring-ink-600"
      title={title ?? label}
    >
      <svg viewBox="0 0 24 12" className={`h-3 w-7 ${look.text}`} aria-hidden>
        <path
          d="M0 6h5l2-4 3 8 2.5-6 2 3H24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className={look.text}>{label}</span>
      <span className="text-muted">{detail}</span>
      <span className={`h-2.5 w-2.5 rounded-full ${look.dot}`} aria-hidden />
    </span>
  )
}

function fmt(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${Math.round(ms / 100) / 10} s`
}
