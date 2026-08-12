import { useEffect, useMemo, useState } from 'react'
import { IS_MOCK } from '../../lib/env'
import { localCapabilities, subscribeLocalCapabilities } from '../../bus/clientCapabilities'
import { useClassroom } from '../../store/classroom'
import { mockRoster, parseRoster, rosterText } from './lessonSetup'
import type { LessonSetup } from './lessonSetup'

export function SetupPanel({ value, onChange }: {
  value: LessonSetup
  onChange: (value: LessonSetup) => void
}) {
  const lesson = useClassroom((state) => state.lesson)
  const status = useClassroom((state) => state.status)
  const [text, setText] = useState(() => rosterText(value.roster))
  const [capabilities, setCapabilities] = useState(() => localCapabilities())
  const parsed = useMemo(() => parseRoster(text), [text])

  useEffect(() => subscribeLocalCapabilities(() => setCapabilities(localCapabilities())), [])
  useEffect(() => {
    if (value.lessonId || !lesson?.lessonId) return
    onChange({ ...value, lessonId: lesson.lessonId, classId: value.classId || lesson.classId })
  }, [lesson?.classId, lesson?.lessonId, onChange, value])

  const rosterReady = !parsed.error && parsed.roster.length >= 1
  const attended = value.attendanceIds.length
  const micReady = capabilities.microphone === true
  const roomReady = status?.readiness === 'ready' && status.liveness === 'live'

  const commitRoster = (nextText: string) => {
    setText(nextText)
    const next = parseRoster(nextText)
    if (next.error) return
    const existingAttendance = new Set(value.attendanceIds)
    const attendanceIds = next.roster
      .filter(({ id }) => existingAttendance.has(id) || value.roster.length === 0)
      .map(({ id }) => id)
    onChange({ ...value, roster: next.roster, attendanceIds })
  }

  return (
    <section className="rounded-3xl bg-ink-800 p-5 ring-2 ring-ink-600" aria-labelledby="setup-title">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p id="setup-title" className="text-xs font-bold tracking-[0.18em] text-muted uppercase">Class setup</p>
          <h2 className="mt-1 font-display text-xl font-extrabold">Who is here today?</h2>
        </div>
        <span className="rounded-full bg-ink-900 px-3 py-1 text-xs font-bold text-muted ring-2 ring-ink-700">
          {value.roster.length} learners · {attended} present
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <Field label="Lesson id" value={value.lessonId} placeholder="loaded lesson" onChange={(lessonId) => onChange({ ...value, lessonId })} />
        <Field label="Class id" value={value.classId} placeholder="class-7a" onChange={(classId) => onChange({ ...value, classId })} />
      </div>

      <label className="mt-4 block text-sm font-bold text-cream" htmlFor="roster-input">
        Pseudonymous roster <span className="font-normal text-muted">— learner-id, display name, optional seat</span>
      </label>
      <textarea
        id="roster-input"
        value={text}
        rows={5}
        spellCheck={false}
        placeholder={'learner-01, Learner 01, A1\nlearner-02, Learner 02, A2'}
        onChange={(event) => commitRoster(event.target.value)}
        className="mt-2 w-full resize-y rounded-2xl bg-ink-900 p-3 font-mono text-sm text-cream ring-2 ring-ink-700 placeholder:text-muted/60 focus:ring-amber"
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className={`text-xs ${parsed.error ? 'font-bold text-coral' : 'text-muted'}`} role={parsed.error ? 'alert' : undefined}>
          {parsed.error ?? 'Use classroom pseudonyms; do not paste sensitive student records.'}
        </p>
        <label className="cursor-pointer rounded-xl bg-ink-700 px-3 py-2 text-xs font-bold ring-2 ring-ink-500 hover:bg-ink-600">
          Import .csv/.txt
          <input
            type="file"
            accept=".csv,.txt,text/csv,text/plain"
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void file.text().then(commitRoster)
              event.target.value = ''
            }}
          />
        </label>
      </div>

      {rosterReady ? (
        <details className="mt-3 rounded-2xl bg-ink-900 ring-2 ring-ink-700">
          <summary className="cursor-pointer px-4 py-3 text-sm font-bold">Attendance · {attended}/{value.roster.length} present</summary>
          <div className="grid max-h-48 grid-cols-2 gap-2 overflow-y-auto border-t-2 border-ink-700 p-3">
            {value.roster.map((learner) => {
              const checked = value.attendanceIds.includes(learner.id)
              return (
                <label key={learner.id} className="flex min-h-11 items-center gap-2 rounded-xl bg-ink-800 px-3 text-sm">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onChange({
                      ...value,
                      attendanceIds: checked
                        ? value.attendanceIds.filter((id) => id !== learner.id)
                        : [...value.attendanceIds, learner.id],
                    })}
                    className="h-5 w-5 accent-amber"
                  />
                  <span className="truncate">{learner.displayName}</span>
                </label>
              )
            })}
          </div>
        </details>
      ) : null}

      <div className="mt-4 grid grid-cols-3 gap-2 text-xs font-bold">
        <Check ok={roomReady} label="Stage + speaker" />
        <Check ok={micReady} label="Answer mic" />
        <Check ok={rosterReady && attended > 0} label="Roster" />
      </div>

      {IS_MOCK && value.roster.length === 0 ? (
        <button type="button" onClick={() => commitRoster(rosterText(mockRoster()))} className="mt-3 min-h-11 w-full rounded-xl bg-violet/15 font-bold text-violet ring-2 ring-violet/45">
          Load 20 synthetic learners
        </button>
      ) : null}
    </section>
  )
}

function Field({ label, value, placeholder, onChange }: { label: string; value: string; placeholder: string; onChange: (value: string) => void }) {
  return <label className="text-sm font-bold">{label}<input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} className="mt-1.5 min-h-11 w-full rounded-xl bg-ink-900 px-3 font-mono text-sm font-normal ring-2 ring-ink-700 placeholder:text-muted/60 focus:ring-amber" /></label>
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`rounded-xl px-2 py-2 text-center ring-2 ${ok ? 'bg-mint/12 text-mint ring-mint/35' : 'bg-amber/12 text-amber ring-amber/35'}`}>{ok ? 'Ready' : 'Needed'} · {label}</span>
}
