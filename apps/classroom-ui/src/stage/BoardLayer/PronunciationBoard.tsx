/**
 * `pronunciation` — the word, and how each sound went.
 *
 * Scoring does not exist yet. This board renders the three states the protocol
 * defines (`pending` / `good` / `retry`) so the service can drive it the day it
 * lands, and so a lesson can hand-author a worked example in the meantime.
 *
 * The design problem is that a phoneme chip is meaningless to an eight-year-old
 * — /ɑː/ is not something a child reads. So the IPA is the *small* text and the
 * state is carried by colour, shape and a glyph a child already knows: a tick
 * for a sound they got, a circular arrow for one to try again, an empty ring
 * for one not reached. Read at 8 m the row is a row of ticks and arrows; read
 * up close it is phonetics. Both audiences are served without a legend.
 *
 * There is no interaction: a pronunciation activity is graded by speech, which
 * arrives on `student.speech.final` from the console's hold-to-talk. Nothing
 * here is tappable, because a tap that could burn the child's one graded answer
 * would be worse than no tap at all.
 */
import type { PronunciationProps } from '@contracts'
import { BoardShell, cx } from './parts'

type Status = 'pending' | 'good' | 'retry'

const LOOK: Record<Status, { chip: string; symbol: string; badge: string }> = {
  good: {
    chip: 'border-mint bg-mint/20 text-mint',
    symbol: 'text-mint',
    badge: 'bg-mint text-ink-900',
  },
  retry: {
    chip: 'border-rose bg-rose/20 text-rose animate-breathe',
    symbol: 'text-rose',
    badge: 'bg-rose text-ink-900',
  },
  pending: {
    chip: 'border-ink-500 bg-ink-800/70 text-muted',
    symbol: 'text-muted',
    badge: 'bg-ink-600 text-muted',
  },
}

const GLYPH: Record<Status, string> = {
  // tick · circular arrow · empty ring
  good: 'M5 13l4 4L19 7',
  retry: 'M20 12a8 8 0 1 1-2.3-5.6M19 3v5h-5',
  pending: '',
}

export function PronunciationBoard({ props }: { props: PronunciationProps }) {
  const phonemes = props.phonemes ?? []
  const good = phonemes.filter((p) => p.status === 'good').length
  const retry = phonemes.filter((p) => p.status === 'retry').length
  const done = good + retry

  return (
    <BoardShell justify="between">
      {/* The word, as big as the board allows. This is what the child says. */}
      <h2 className="animate-rise t-board-xl text-center font-display font-extrabold tracking-tight text-cream">
        {props.word}
      </h2>

      <div className="flex w-full flex-wrap items-start justify-center gap-[1.4vh_1vw]">
        {phonemes.map((p, i) => {
          const status = (p.status ?? 'pending') as Status
          const look = LOOK[status]
          return (
            <div
              key={`${p.symbol}-${i}`}
              style={{ animationDelay: `${i * 70}ms` }}
              className={cx(
                'animate-rise relative flex min-w-[7vw] flex-col items-center gap-[0.8vh]',
                'rounded-[1.3rem] border-4 px-[1.1vw] py-[1.6vh]',
                look.chip,
              )}
            >
              <span
                className={cx(
                  'font-mono text-[clamp(1.7rem,3.4vw,3.6rem)] leading-none font-bold',
                  look.symbol,
                )}
              >
                {p.symbol}
              </span>
              <span
                className={cx(
                  'flex h-[4vh] w-[4vh] min-h-[24px] min-w-[24px] items-center justify-center rounded-full',
                  look.badge,
                )}
                aria-label={status}
              >
                {GLYPH[status] ? (
                  <svg
                    viewBox="0 0 24 24"
                    className="h-[2.4vh] w-[2.4vh] min-h-[14px] min-w-[14px]"
                    aria-hidden
                  >
                    <path
                      d={GLYPH[status]}
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : null}
              </span>
            </div>
          )
        })}
      </div>

      {/* Progress, without a number a child has to decode. */}
      <div className="flex w-[62%] min-w-[38vw] items-center gap-[1vw]">
        <div className="h-[1.6vh] min-h-[10px] flex-1 overflow-hidden rounded-full bg-ink-700">
          <div
            className={cx(
              'h-full rounded-full transition-[width] duration-500 ease-out',
              retry ? 'bg-rose' : 'bg-mint',
            )}
            style={{ width: phonemes.length ? `${(done / phonemes.length) * 100}%` : '0%' }}
          />
        </div>
        <span className="font-display text-[clamp(1rem,1.7vw,1.8rem)] font-extrabold whitespace-nowrap text-muted">
          {good}/{phonemes.length || 0} sounds
        </span>
      </div>
    </BoardShell>
  )
}
