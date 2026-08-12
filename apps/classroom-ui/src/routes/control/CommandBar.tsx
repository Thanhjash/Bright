/** Autonomous-classroom safety controls: routine steering stays disclosed. */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ControlCommand } from '@contracts'
import { useBus } from '../../bus'
import { useClassroom } from '../../store/classroom'
import { localCapabilities, subscribeLocalCapabilities } from '../../bus/clientCapabilities'
import type { LessonSetup } from './lessonSetup'

export function CommandBar({ setup }: { setup: LessonSetup }) {
  const bus = useBus()
  const lessonStage = useClassroom((state) => state.lesson?.stage)
  const session = useClassroom((state) => state.session)
  const status = useClassroom((state) => state.status)
  const [startPending, setStartPending] = useState(false)
  const [startError, setStartError] = useState('')
  const [capabilities, setCapabilities] = useState(() => localCapabilities())
  const startRequest = useRef<string | null>(null)

  const running = session?.status === 'RUNNING'
    || (!session && Boolean(lessonStage && !['IDLE', 'DONE', 'READY'].includes(lessonStage)))
  const paused = session?.status === 'PAUSED' || session?.status === 'RECOVERING'
  const roomReady = status?.liveness === 'live' && status.readiness === 'ready'
  const micReady = capabilities.microphone === true
  const setupReady = setup.roster.length >= 1 && setup.attendanceIds.length >= 1
  const teachable = roomReady && micReady && setupReady

  useEffect(() => subscribeLocalCapabilities(() => setCapabilities(localCapabilities())), [])

  useEffect(() => bus.on('lesson.started', ({ requestId }) => {
    if (requestId !== startRequest.current) return
    startRequest.current = null
    setStartPending(false)
  }), [bus])

  useEffect(() => bus.on('error', ({ code, message }) => {
    if (!startRequest.current) return
    if (!['no_lesson', 'lesson_already_running', 'invalid_start_index', 'invalid_lesson_start', 'not_teachable', 'roster_required', 'lesson_mismatch', 'class_mismatch'].includes(code)) return
    startRequest.current = null
    setStartPending(false)
    setStartError(message)
  }), [bus])

  const command = useCallback((cmd: ControlCommand, reason: string) => {
    bus.send('control.command', { cmd, arg: reason })
  }, [bus])

  const start = useCallback(() => {
    if (!teachable || startPending || running) return
    const requestId = crypto.randomUUID()
    setStartError('')
    startRequest.current = requestId
    setStartPending(true)
    bus.send('lesson.start', {
      requestId,
      ...(setup.lessonId ? { lessonId: setup.lessonId } : {}),
      ...(setup.classId ? { classId: setup.classId } : {}),
      roster: setup.roster,
      attendanceIds: setup.attendanceIds,
    })
    window.setTimeout(() => {
      if (startRequest.current !== requestId) return
      startRequest.current = null
      setStartPending(false)
    }, 10_000)
  }, [bus, running, setup, startPending, teachable])

  return (
    <section className="rounded-3xl bg-ink-800 p-4 ring-2 ring-ink-600" aria-labelledby="safety-controls-title">
      <p id="safety-controls-title" className="mb-3 text-xs font-bold tracking-[0.18em] text-muted uppercase">
        Classroom safety
      </p>

      {!running && !paused ? (
        <button
          type="button"
          onClick={start}
          disabled={!teachable || startPending}
          data-testid="start-lesson"
          className="flex min-h-20 w-full items-center justify-between rounded-2xl bg-mint/18 px-5 text-left text-mint ring-2 ring-mint/55 transition hover:bg-mint/25 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-45"
        >
          <span>
            <span className="block font-display text-xl font-extrabold">{startPending ? 'Starting…' : 'Start autonomous lesson'}</span>
            <span className="block text-sm text-muted">
              {teachable ? 'Bright owns pacing, participation and recovery.' : !setupReady ? 'Add the roster and mark attendance.' : !micReady ? 'Check the answer-station microphone.' : status?.reason ?? 'Complete room preflight first.'}
            </span>
          </span>
          <PlayIcon />
        </button>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          <SafetyButton label="Pause" hint="Hold the lesson" tone="amber" onClick={() => command('pause', 'facilitator_pause')} />
          <SafetyButton label="Resume" hint="Continue safely" tone="mint" disabled={!paused} onClick={() => command('resume', 'facilitator_resume')} />
          <SafetyButton label="Emergency stop" hint="Stop voice and activity" tone="coral" onClick={() => command('takeover', 'facilitator_emergency')} />
        </div>
      )}

      {startError ? <p role="alert" className="mt-3 rounded-xl bg-coral/15 p-3 text-sm font-bold text-coral ring-2 ring-coral/45">{startError}</p> : null}

      <details className="mt-3 rounded-2xl bg-ink-900 ring-2 ring-ink-700">
        <summary className="cursor-pointer px-4 py-3 text-sm font-bold text-muted focus-visible:text-cream">
          Recovery tools
        </summary>
        <div className="grid grid-cols-3 gap-2 border-t-2 border-ink-700 p-3">
          <SmallButton label="Repeat" onClick={() => command('repeat', 'facilitator_recovery_repeat')} />
          <SmallButton label="Back" onClick={() => command('back', 'facilitator_recovery_back')} />
          <SmallButton label="Skip" onClick={() => command('skip', 'facilitator_recovery_skip')} />
        </div>
      </details>
    </section>
  )
}

function SafetyButton({ label, hint, tone, disabled, onClick }: {
  label: string
  hint: string
  tone: 'amber' | 'mint' | 'coral'
  disabled?: boolean
  onClick: () => void
}) {
  const colours = {
    amber: 'bg-amber/18 text-amber ring-amber/55',
    mint: 'bg-mint/18 text-mint ring-mint/55',
    coral: 'bg-coral/18 text-coral ring-coral/60',
  }
  return (
    <button type="button" disabled={disabled} onClick={onClick} className={`min-h-[5.5rem] rounded-2xl p-3 text-left ring-2 transition hover:brightness-125 active:scale-[0.98] disabled:opacity-35 ${colours[tone]}`}>
      <span className="block font-display text-lg font-extrabold">{label}</span>
      <span className="mt-1 block text-xs text-muted">{hint}</span>
    </button>
  )
}

function SmallButton({ label, onClick }: { label: string; onClick: () => void }) {
  return <button type="button" onClick={onClick} className="min-h-12 rounded-xl bg-ink-700 px-3 font-bold text-cream ring-2 ring-ink-500 hover:bg-ink-600">{label}</button>
}

function PlayIcon() {
  return <svg viewBox="0 0 24 24" className="h-8 w-8" aria-hidden><path d="M7 4l13 8-13 8z" fill="currentColor" /></svg>
}
