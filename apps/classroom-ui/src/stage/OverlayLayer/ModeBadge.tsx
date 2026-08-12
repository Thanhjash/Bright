import { useModeBadge } from '../../store/classroom'

/**
 * PROTOCOL.md §7 / docs/3-design/runtime-topology.md §4: shown **only** in DEGRADED or OFFLINE, never
 * in FULL. Calm, small, honest — the teacher is never asked to care, but the
 * room should not be lied to either.
 */
const COPY: Record<'DEGRADED' | 'OFFLINE', { label: string; tone: string }> = {
  DEGRADED: { label: 'Lesson mode', tone: 'text-amber ring-amber/55' },
  OFFLINE: { label: 'Offline lesson', tone: 'text-coral ring-coral/55' },
}

export function ModeBadge() {
  const badge = useModeBadge()
  if (!badge) return null

  const { label, tone } = COPY[badge]
  return (
    <span
      className={`animate-pop flex items-center gap-[0.7vw] rounded-full bg-ink-950/78 px-[1.6vw] py-[1vh] font-display text-[clamp(0.9rem,1.4vw,1.5rem)] font-extrabold tracking-wide ring-3 backdrop-blur-sm ${tone}`}
      title={badge}
    >
      <span className="h-[1.2vh] w-[1.2vh] min-h-[8px] min-w-[8px] rounded-full bg-current" />
      {label}
    </span>
  )
}
