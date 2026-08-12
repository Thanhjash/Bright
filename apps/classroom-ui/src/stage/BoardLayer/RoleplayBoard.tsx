/**
 * `roleplay` — who we both are, where we are, and what to say.
 *
 * This is the board a child *reads from* while speaking, so the hierarchy is
 * inverted from every other scene: the target phrases are the largest thing on
 * screen, not the title. A child who cannot read their line cannot do the
 * activity, and at 8 m a "helper" line set in caption type is not there at all.
 *
 * The two roles are shown as a facing pair, because that is the thing being
 * taught — a conversation has two sides and you are one of them. The student's
 * side is the lit one.
 *
 * Tapping a phrase enlarges it and dims the rest: thirty children round one
 * screen need to know which line is being practised right now. That selection
 * is deliberately **local and silent** — it emits no event, because core allows
 * exactly one graded answer per activity and a roleplay is graded by speech.
 */
import { useEffect, useMemo, useState } from 'react'
import type { RoleplayProps } from '@contracts'
import { BoardShell, cx } from './parts'

export function RoleplayBoard({ props }: { props: RoleplayProps }) {
  const phrases = props.targetPhrases ?? []
  const signature = useMemo(() => phrases.join('|'), [phrases])
  const [picked, setPicked] = useState<number | null>(null)
  useEffect(() => setPicked(null), [signature])

  return (
    <BoardShell align="stretch" justify="between">
      {/* Where we are, and who we each are. */}
      <div className="flex w-full items-stretch justify-center gap-[1.4vw]">
        <Role
          label="I am"
          name={props.aiRole}
          tone="teacher"
          glyph="M12 12a4.2 4.2 0 1 0 0-8.4 4.2 4.2 0 0 0 0 8.4ZM4.5 21a7.5 7.5 0 0 1 15 0"
        />
        <Where environment={props.environment} />
        <Role
          label="You are"
          name={props.studentRole}
          tone="student"
          glyph="M12 12a4.2 4.2 0 1 0 0-8.4 4.2 4.2 0 0 0 0 8.4ZM4.5 21a7.5 7.5 0 0 1 15 0"
        />
      </div>

      {/* What to say. The biggest thing on the board, by design. */}
      <div className="flex min-h-0 w-full flex-1 flex-col justify-center gap-[1.6vh]">
        {phrases.map((phrase, i) => {
          const active = picked === i
          const dimmed = picked !== null && !active
          return (
            <button
              key={`${phrase}-${i}`}
              type="button"
              onPointerDown={() => setPicked((p) => (p === i ? null : i))}
              style={{ animationDelay: `${i * 80}ms`, touchAction: 'none' }}
              className={cx(
                'animate-rise relative flex items-center gap-[1.2vw] rounded-[1.75rem] border-4 px-[1.6vw] py-[1.8vh] text-left',
                'transition-[transform,opacity,border-color,background-color] duration-200 ease-out',
                active
                  ? 'scale-[1.02] border-amber bg-amber/20'
                  : 'border-ink-500/70 bg-ink-800/60 hover:border-amber/60',
                dimmed && 'opacity-45',
              )}
            >
              {/* A speech-bubble tail, so the line reads as something spoken. */}
              <span
                className={cx(
                  'flex h-[5vh] w-[5vh] min-h-[30px] min-w-[30px] shrink-0 items-center justify-center rounded-full',
                  active ? 'bg-amber text-ink-900' : 'bg-ink-600 text-muted',
                )}
                aria-hidden
              >
                <svg viewBox="0 0 24 24" className="h-[3vh] w-[3vh] min-h-[18px] min-w-[18px]">
                  <path
                    d="M21 12a8 8 0 0 1-8 8H4l2.2-2.9A8 8 0 1 1 21 12Z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              <span
                className={cx(
                  'font-display leading-tight font-extrabold text-balance',
                  'text-[clamp(1.5rem,3vw,3.2rem)]',
                  active ? 'text-cream' : 'text-cream/90',
                )}
              >
                {phrase}
              </span>
            </button>
          )
        })}
      </div>
    </BoardShell>
  )
}

function Role({
  label,
  name,
  tone,
  glyph,
}: {
  label: string
  name: string
  tone: 'teacher' | 'student'
  glyph: string
}) {
  const student = tone === 'student'
  return (
    <div
      className={cx(
        'animate-rise flex flex-1 items-center gap-[0.9vw] rounded-[1.6rem] border-4 px-[1.2vw] py-[1.4vh]',
        student ? 'border-amber bg-amber/16' : 'border-sky/60 bg-sky/10',
      )}
    >
      <span
        className={cx(
          'flex h-[6vh] w-[6vh] min-h-[34px] min-w-[34px] shrink-0 items-center justify-center rounded-full',
          student ? 'bg-amber text-ink-900' : 'bg-sky text-ink-900',
        )}
        aria-hidden
      >
        <svg viewBox="0 0 24 24" className="h-[3.6vh] w-[3.6vh] min-h-[20px] min-w-[20px]">
          <path d={glyph} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      </span>
      <span className="min-w-0">
        <span
          className={cx(
            'block text-[clamp(0.8rem,1.15vw,1.2rem)] font-extrabold tracking-[0.16em] uppercase',
            student ? 'text-amber' : 'text-sky',
          )}
        >
          {label}
        </span>
        <span className="block truncate font-display text-[clamp(1.2rem,2.3vw,2.5rem)] leading-tight font-extrabold text-cream">
          {name}
        </span>
      </span>
    </div>
  )
}

function Where({ environment }: { environment: string }) {
  return (
    <div className="animate-rise flex shrink-0 flex-col items-center justify-center rounded-[1.6rem] bg-ink-800/70 px-[1.4vw] py-[1.4vh]">
      <span className="text-[clamp(0.8rem,1.15vw,1.2rem)] font-extrabold tracking-[0.16em] text-muted uppercase">
        at the
      </span>
      <span className="font-display text-[clamp(1.2rem,2.3vw,2.5rem)] leading-tight font-extrabold text-cream">
        {environment}
      </span>
    </div>
  )
}
