/**
 * Live transcript — what was said, what changed, what we sent.
 *
 * Auto-scrolls, but only while the facilitator is already at the bottom:
 * yanking the view away from someone who scrolled back to read is worse than
 * missing a line.
 */
import { useEffect, useRef } from 'react'
import { useClassroom } from '../../store/classroom'
import type { TranscriptKind } from '../../store/classroom'

const LOOK: Record<TranscriptKind, { who: string; cls: string }> = {
  teacher: { who: 'Teacher', cls: 'border-amber/70 text-cream' },
  student: { who: 'Student', cls: 'border-sky/70 text-cream' },
  system: { who: 'System', cls: 'border-ink-500 text-muted' },
}

export function TranscriptPanel() {
  const transcript = useClassroom((s) => s.transcript)
  const scroller = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  useEffect(() => {
    const el = scroller.current
    if (el && pinned.current) el.scrollTop = el.scrollHeight
  }, [transcript])

  function onScroll() {
    const el = scroller.current
    if (!el) return
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
  }

  return (
    <section className="flex min-h-0 flex-col rounded-3xl bg-ink-800 ring-2 ring-ink-600">
      <div className="flex items-center justify-between border-b-3 border-ink-700 px-5 py-3.5">
        <p className="text-xs font-bold tracking-[0.18em] text-muted uppercase">Transcript</p>
        <span className="text-xs text-muted">{transcript.length} lines</span>
      </div>

      <div
        ref={scroller}
        onScroll={onScroll}
        className="min-h-0 flex-1 space-y-2.5 overflow-y-auto p-5"
      >
        {transcript.length === 0 ? (
          <p className="text-muted">Nothing yet. Lines appear as the lesson runs.</p>
        ) : null}

        {transcript.map((entry) => {
          const look = LOOK[entry.kind]
          return (
            <div key={entry.id} className={`border-l-4 pl-3.5 ${look.cls}`}>
              <div className="flex items-baseline gap-2.5">
                <span className="text-xs font-bold tracking-wider text-muted uppercase">
                  {look.who}
                </span>
                <span className="font-mono text-xs text-muted">{clock(entry.ts)}</span>
              </div>
              <p className="text-lg leading-snug">{entry.text}</p>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function clock(ts: number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
