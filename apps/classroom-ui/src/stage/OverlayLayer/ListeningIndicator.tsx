import { useEffect, useState } from 'react'
import { subscribeAnswerStationActivity } from '../../speech/answerStationActivity'
import type { AnswerStationActivity } from '../../speech/answerStationActivity'
import { useClassroom } from '../../store/classroom'

/** Classroom turn cue. Attribution remains the server-issued assignment. */
export function ListeningIndicator() {
  const assignment = useClassroom((state) => state.assignment)
  const capture = useClassroom((state) => state.capture)
  const [activity, setActivity] = useState<AnswerStationActivity>({ phase: 'idle', at: 0 })

  useEffect(() => subscribeAnswerStationActivity(setActivity), [])

  if (!assignment || assignment.captureScope !== 'answer_station') return null
  const correlated = activity.assignmentId === assignment.assignmentId
    && (!capture || activity.captureId === capture.captureId)
  const phase = correlated ? activity.phase : 'assigned'
  const copy = cue(phase, safeTargetLabel(assignment.targetDisplayName ?? assignment.targetId))

  return (
    <div className={`animate-pop flex items-center gap-[1.2vw] rounded-full bg-ink-950/88 px-[2vw] py-[1.2vh] ring-3 backdrop-blur-sm ${copy.tone}`}>
      <span className="flex h-[3.6vh] items-end gap-[0.35vw]" aria-hidden>
        {[0, 1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className={`w-[0.55vw] min-w-[5px] rounded-full ${copy.bar}`}
            style={{
              height: `${[46, 74, 100, 68, 40][i]}%`,
              animation: phase === 'listening' ? 'listen 1.1s ease-in-out infinite' : undefined,
              animationDelay: `${i * 110}ms`,
              transformOrigin: 'bottom',
            }}
          />
        ))}
      </span>
      <span className="font-display text-[clamp(1rem,1.7vw,1.9rem)] font-extrabold tracking-tight">
        {copy.text}
      </span>
    </div>
  )
}
function cue(phase: AnswerStationActivity['phase'], target: string | null) {
  const called = target ? `${target}, come to the answer station · press Ready` : 'Come to the answer station · press Ready'
  switch (phase) {
    case 'opening':
      return { text: 'Get ready…', tone: 'text-amber ring-amber/60', bar: 'bg-amber' }
    case 'listening':
      return { text: 'Speak now', tone: 'text-mint ring-mint/60', bar: 'bg-mint' }
    case 'thinking':
    case 'waiting':
      return { text: 'Thank you — Bright is checking', tone: 'text-sky ring-sky/60', bar: 'bg-sky' }
    case 'error':
      return { text: 'Please wait for Bright', tone: 'text-amber ring-amber/60', bar: 'bg-amber' }
    default:
      return { text: called, tone: 'text-mint ring-mint/60', bar: 'bg-mint' }
  }
}

/**
 * Core exposes only the selected pseudonym, never the roster, for the current
 * physical turn. Sanitize again before projection; fall back to targetId for
 * older fixtures.
 */
function safeTargetLabel(targetId?: string): string | null {
  const clean = targetId
    ?.normalize('NFKC')
    .replace(/[^\p{L}\p{N}_-]+/gu, ' ')
    .trim()
    .slice(0, 32)
  if (!clean) return null
  return clean
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.length <= 3 && /^\d+$/.test(part)
      ? part
      : part.charAt(0).toLocaleUpperCase() + part.slice(1))
    .join(' ')
}
