/**
 * Where the lesson is, right now. Everything on this panel comes from the
 * server; nothing is inferred locally.
 */
import { SCENE_LABEL, isSceneKind } from '../../lib/scene'
import { selectStudentName, selectSubtitle, useClassroom } from '../../store/classroom'
import type { Mode } from '@contracts'

const MODE_LOOK: Record<Mode, string> = {
  FULL: 'bg-mint/20 text-mint ring-mint/45',
  DEGRADED: 'bg-amber/20 text-amber ring-amber/45',
  OFFLINE: 'bg-coral/20 text-coral ring-coral/45',
}

export function StatusPanel() {
  const lesson = useClassroom((s) => s.lesson)
  const scene = useClassroom((s) => s.scene)
  const mode = useClassroom((s) => s.mode)
  const modeReason = useClassroom((s) => s.modeReason)
  const stateVersion = useClassroom((s) => s.stateVersion)
  const listening = useClassroom((s) => s.scene?.overlay?.listening === true)
  const student = useClassroom(selectStudentName)
  const subtitle = useClassroom(selectSubtitle)
  const awaitingSnapshot = useClassroom((s) => s.awaitingSnapshot)

  const index = lesson ? lesson.activityIndex + 1 : 0
  const count = lesson?.activityCount ?? 0
  const pct = count ? Math.round((index / count) * 100) : 0
  const kindLabel = scene && isSceneKind(scene.kind) ? SCENE_LABEL[scene.kind] : (scene?.kind ?? '—')

  return (
    <section className="rounded-3xl bg-ink-800 p-6 ring-2 ring-ink-600">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold tracking-[0.18em] text-muted uppercase">Lesson</p>
          <h1 className="font-display text-3xl leading-tight font-extrabold">
            {lesson?.lessonId ?? 'No lesson loaded'}
          </h1>
          <p className="mt-1 text-lg text-muted">
            Class {lesson?.classId ?? '—'}
            {student ? <> · student <span className="font-bold text-cream">{student}</span></> : null}
          </p>
        </div>
        <span
          className={`rounded-full px-4 py-2 text-sm font-extrabold tracking-wider ring-2 ${MODE_LOOK[mode]}`}
          title={modeReason || undefined}
        >
          {mode}
        </span>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Stage" value={lesson?.stage ?? '—'} />
        <Stat label="Activity" value={count ? `${index} of ${count}` : '—'} />
        <Stat label="Scene" value={kindLabel} />
        <Stat label="State version" value={String(stateVersion)} />
      </div>

      <div className="mt-5 h-2.5 w-full overflow-hidden rounded-full bg-ink-700">
        <div
          className="h-full rounded-full bg-amber transition-[width] duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        {listening ? <Flag tone="mint">Listening to student</Flag> : null}
        {awaitingSnapshot ? <Flag tone="amber">Waiting for snapshot</Flag> : null}
        {modeReason && mode !== 'FULL' ? <Flag tone="amber">{modeReason}</Flag> : null}
      </div>

      <p className="mt-5 min-h-[3.5rem] rounded-2xl bg-ink-900 p-4 text-lg leading-snug text-cream ring-2 ring-ink-700">
        {subtitle || <span className="text-muted">Nothing on the subtitle bar</span>}
      </p>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-ink-900 p-4 ring-2 ring-ink-700">
      <p className="text-xs font-bold tracking-[0.16em] text-muted uppercase">{label}</p>
      <p className="mt-1 font-display text-xl leading-tight font-extrabold" title={value}>
        {value}
      </p>
    </div>
  )
}

function Flag({ tone, children }: { tone: 'mint' | 'amber'; children: React.ReactNode }) {
  const cls =
    tone === 'mint' ? 'bg-mint/18 text-mint ring-mint/40' : 'bg-amber/18 text-amber ring-amber/40'
  return (
    <span className={`rounded-full px-3.5 py-1.5 text-sm font-bold ring-2 ${cls}`}>{children}</span>
  )
}
