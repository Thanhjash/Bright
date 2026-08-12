/**
 * The six commands, as big touch targets.
 *
 * They send `control.command` and nothing else — the console does not change
 * local state to match, because it is not the authority. Confirmation is the
 * scene actually changing on the projector.
 *
 * The sent command is echoed into the transcript so a facilitator can see
 * their tap registered even if core is slow to answer.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ControlCommand } from '@contracts'
import { useBus } from '../../bus'
import { useClassroom } from '../../store/classroom'

interface CommandSpec {
  cmd: ControlCommand
  label: string
  hint: string
  tone: 'plain' | 'go' | 'warn' | 'danger'
  icon: string
}

const COMMANDS: CommandSpec[] = [
  { cmd: 'pause', label: 'Pause', hint: 'Hold everything', tone: 'warn', icon: 'M8 5h3v14H8zM13 5h3v14h-3z' },
  { cmd: 'resume', label: 'Resume', hint: 'Carry on', tone: 'go', icon: 'M7 4l13 8-13 8z' },
  { cmd: 'repeat', label: 'Repeat', hint: 'Say it again', tone: 'plain', icon: 'M4 12a8 8 0 0 1 13.7-5.7M20 12a8 8 0 0 1-13.7 5.7M18 3v5h-5M6 21v-5h5' },
  { cmd: 'back', label: 'Back', hint: 'Previous activity', tone: 'plain', icon: 'M15 5l-7 7 7 7' },
  { cmd: 'skip', label: 'Skip', hint: 'Next activity', tone: 'plain', icon: 'M9 5l7 7-7 7' },
  { cmd: 'takeover', label: 'Take over', hint: 'You teach, it stops', tone: 'danger', icon: 'M12 3l7 4v6c0 4.4-3 7.4-7 8-4-.6-7-3.6-7-8V7z' },
]

const TONE: Record<CommandSpec['tone'], string> = {
  plain: 'bg-ink-700 ring-ink-500 hover:bg-ink-600 text-cream',
  go: 'bg-mint/18 ring-mint/50 hover:bg-mint/28 text-mint',
  warn: 'bg-amber/18 ring-amber/50 hover:bg-amber/28 text-amber',
  danger: 'bg-coral/18 ring-coral/55 hover:bg-coral/28 text-coral',
}

export function CommandBar() {
  const bus = useBus()
  const log = useClassroom((s) => s.log)
  const lessonStage = useClassroom((s) => s.lesson?.stage)
  const [flash, setFlash] = useState<ControlCommand | null>(null)
  const [startState, setStartState] = useState<'idle' | 'pending' | 'started'>('idle')
  const startRequest = useRef<string | null>(null)

  useEffect(
    () => bus.on('lesson.started', ({ requestId }) => {
      if (requestId !== startRequest.current)
        return
      setStartState('started')
      startRequest.current = null
    }),
    [bus],
  )
  useEffect(
    () => bus.on('error', ({ code }) => {
      if (!startRequest.current || !['no_lesson', 'lesson_already_running', 'invalid_start_index', 'invalid_lesson_start'].includes(code))
        return
      startRequest.current = null
      setStartState(code === 'lesson_already_running' ? 'started' : 'idle')
    }),
    [bus],
  )
  useEffect(() => {
    setStartState((current) => {
      if (current === 'pending')
        return current
      return !lessonStage || lessonStage === 'IDLE' || lessonStage === 'DONE' ? 'idle' : 'started'
    })
  }, [lessonStage])

  const startLesson = useCallback(() => {
    if (startState === 'pending')
      return
    const requestId = crypto.randomUUID()
    startRequest.current = requestId
    setStartState('pending')
    bus.send('lesson.start', { requestId })
    log('system', 'sent: lesson.start')
    window.setTimeout(() => {
      if (startRequest.current !== requestId)
        return
      startRequest.current = null
      setStartState('idle')
      log('system', 'lesson.start received no acknowledgement; safe to retry')
    }, 10_000)
  }, [bus, log, startState])

  const run = useCallback(
    (spec: CommandSpec) => {
      setFlash(spec.cmd)
      window.setTimeout(() => setFlash((c) => (c === spec.cmd ? null : c)), 260)
      bus.send('control.command', { cmd: spec.cmd })
      log('system', `sent: ${spec.cmd}`)
    },
    [bus, log],
  )

  return (
    <section className="rounded-3xl bg-ink-800 p-5 ring-2 ring-ink-600">
      <button
        type="button"
        onPointerDown={startLesson}
        disabled={startState !== 'idle'}
        className="mb-5 flex min-h-20 w-full items-center justify-between rounded-2xl bg-mint/18 px-5 text-left text-mint ring-2 ring-mint/50 transition active:scale-[0.99] disabled:cursor-wait disabled:opacity-60"
      >
        <span>
          <span className="block font-display text-xl font-extrabold">
            {startState === 'pending' ? 'Starting…' : startState === 'started' ? 'Lesson running' : lessonStage === 'DONE' ? 'Restart lesson' : 'Start lesson'}
          </span>
          <span className="block text-sm text-muted">
            {startState === 'started' ? 'Start becomes available again when this lesson ends' : 'Open the loaded lesson at activity one'}
          </span>
        </span>
        <svg viewBox="0 0 24 24" className="h-8 w-8" aria-hidden>
          <path d="M7 4l13 8-13 8z" fill="currentColor" />
        </svg>
      </button>
      <p className="mb-4 text-xs font-bold tracking-[0.18em] text-muted uppercase">Controls</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {COMMANDS.map((spec) => (
          <button
            key={spec.cmd}
            type="button"
            onPointerDown={() => run(spec)}
            className={`flex min-h-[6.5rem] flex-col items-start justify-between gap-2 rounded-2xl p-4 text-left ring-2 transition-[transform,background-color] duration-150 active:scale-[0.97] ${TONE[spec.tone]} ${
              flash === spec.cmd ? 'scale-[0.97] brightness-125' : ''
            }`}
          >
            <svg viewBox="0 0 24 24" className="h-7 w-7" aria-hidden>
              <path
                d={spec.icon}
                fill={spec.cmd === 'pause' || spec.cmd === 'resume' ? 'currentColor' : 'none'}
                stroke="currentColor"
                strokeWidth={spec.cmd === 'pause' || spec.cmd === 'resume' ? 0 : 2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>
              <span className="block font-display text-xl leading-tight font-extrabold">
                {spec.label}
              </span>
              <span className="block text-sm text-muted">{spec.hint}</span>
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}
