/** Core-authored product status: what Bright is doing, why, and what comes next. */
import { useClassroom } from '../../store/classroom'

export function StatusPanel() {
  const lesson = useClassroom((state) => state.lesson)
  const session = useClassroom((state) => state.session)
  const status = useClassroom((state) => state.status)
  const assignment = useClassroom((state) => state.assignment)
  const recovery = useClassroom((state) => state.recovery)
  const mode = useClassroom((state) => state.mode)
  const connection = useClassroom((state) => state.connection.state)

  const index = lesson ? lesson.activityIndex + 1 : 0
  const count = lesson?.activityCount ?? 0
  const progress = count ? Math.round(index / count * 100) : 0
  const phase = session?.status ?? (status?.teachable ? 'READY' : 'SETUP')
  const target = assignment?.responseScope === 'selected_individual'
    ? assignment.targetId ?? 'selected learner'
    : assignment?.responseScope?.replace('_', ' ')

  return (
    <section className="rounded-3xl bg-ink-800 p-5 ring-2 ring-ink-600" aria-labelledby="lesson-status-title">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p id="lesson-status-title" className="text-xs font-bold tracking-[0.18em] text-muted uppercase">Bright is teaching</p>
          <h1 className="truncate font-display text-2xl font-extrabold">{lesson?.lessonId ?? 'Room setup'}</h1>
          <p className="mt-1 text-sm text-muted">Class {lesson?.classId ?? '—'} · {count ? `activity ${index} of ${count}` : 'waiting for lesson'}</p>
        </div>
        <span className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-extrabold ring-2 ${phaseLook(phase)}`}>{phase}</span>
      </div>

      <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-ink-700" aria-label={`${progress}% lesson complete`}>
        <div className="h-full rounded-full bg-amber transition-[width]" style={{ width: `${progress}%` }} />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <Fact label="Now" value={lesson?.stage ?? 'Setup'} />
        <Fact label="With" value={target ?? 'Whole class'} />
        <Fact label="Next" value={recovery?.requiredAction ?? session?.requiredAction ?? 'Bright decides'} />
      </div>

      {recovery ? (
        <div role="alert" className="mt-4 rounded-2xl bg-amber/15 p-4 text-amber ring-2 ring-amber/50">
          <p className="font-display text-lg font-extrabold">Bright paused safely</p>
          <p className="mt-1 text-sm text-cream">{recovery.reason}</p>
          {recovery.requiredAction ? <p className="mt-1 text-sm font-bold">Next: {recovery.requiredAction}</p> : null}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2 text-xs font-bold">
        <Pill ok={connection === 'open' || connection === 'mock'}>{connection === 'open' || connection === 'mock' ? 'Classroom connected' : 'Reconnecting'}</Pill>
        <Pill ok={status?.teachable === true}>{status?.teachable ? 'Room ready' : status?.reason ?? 'Preflight needed'}</Pill>
        <Pill ok={mode === 'FULL'}>{mode === 'FULL' ? 'Adaptive teaching available' : 'Lesson-plan mode'}</Pill>
      </div>
    </section>
  )
}
function Fact({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded-2xl bg-ink-900 p-3 ring-2 ring-ink-700"><p className="text-[0.65rem] font-bold tracking-wider text-muted uppercase">{label}</p><p className="mt-1 truncate font-display text-base font-extrabold" title={value}>{value}</p></div>
}

function Pill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return <span className={`rounded-full px-3 py-1 ring-2 ${ok ? 'bg-mint/12 text-mint ring-mint/35' : 'bg-amber/12 text-amber ring-amber/35'}`}>{children}</span>
}

function phaseLook(phase: string): string {
  if (phase === 'RUNNING') return 'bg-mint/18 text-mint ring-mint/45'
  if (phase === 'PAUSED' || phase === 'RECOVERING') return 'bg-amber/18 text-amber ring-amber/45'
  if (phase === 'COMPLETED') return 'bg-sky/18 text-sky ring-sky/45'
  return 'bg-ink-700 text-muted ring-ink-500'
}
