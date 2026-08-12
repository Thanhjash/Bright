import { useEffect, useState } from 'react'
import type { ChoiceProps } from '@contracts'
import { useBus } from '../../bus'
import { currentResponseCorrelation } from '../../store/classroom'
import { BoardShell, MediaTile, Prompt, cx } from './parts'

/**
 * `choice` — prompt plus options.
 *
 * A tap emits `interaction.choice { optionId }` and paints a press state
 * immediately. It does NOT decide whether the answer was right: `revealed`
 * arrives on the next `scene.update` and is the only source of truth for the
 * green tick and the red cross.
 */
export function ChoiceBoard({ props }: { props: ChoiceProps }) {
  const bus = useBus()
  const [pending, setPending] = useState<string | null>(null)
  const revealed = props.revealed
  const options = props.options ?? []

  // Once the server has spoken, our optimistic state is no longer interesting.
  useEffect(() => {
    if (revealed) setPending(null)
  }, [revealed])

  function choose(optionId: string) {
    if (revealed || pending) return
    const correlation = currentResponseCorrelation()
    if (!correlation) return
    setPending(optionId)
    bus.send('interaction.choice', { optionId, ...correlation })
  }

  return (
    <BoardShell align="stretch" justify="between">
      <Prompt>{props.prompt}</Prompt>

      <div
        className={cx(
          'grid min-h-0 flex-1 grid-rows-1 gap-[1.8vw]',
          options.length >= 4 ? 'grid-cols-4' : options.length === 3 ? 'grid-cols-3' : 'grid-cols-2',
        )}
      >
        {options.map((option, i) => {
          const isCorrect = revealed?.correctId === option.id
          const isChosenWrong = revealed?.chosenId === option.id && !isCorrect
          const dimmed = Boolean(revealed) && !isCorrect && !isChosenWrong

          return (
            <button
              key={option.id}
              type="button"
              disabled={Boolean(revealed)}
              onPointerDown={() => choose(option.id)}
              onKeyDown={(event) => {
                if (event.key !== 'Enter' && event.key !== ' ') return
                event.preventDefault()
                choose(option.id)
              }}
              style={{ animationDelay: `${i * 60}ms` }}
              className={cx(
                'animate-rise card-surface relative flex min-h-0 overflow-hidden p-[2.2vh_1.2vw]',
                'transition-[transform,box-shadow,background-color,border-color,opacity] duration-200 ease-out',
                !revealed && 'cursor-pointer hover:-translate-y-[0.8vh] hover:border-sky/70',
                pending === option.id && !revealed && 'scale-[0.95] border-sky bg-sky/20',
                isCorrect &&
                  'border-mint bg-mint/18 shadow-[0_0_0_0.7vh_rgba(61,220,151,0.3)] -translate-y-[0.8vh]',
                isChosenWrong && 'border-rose bg-rose/18',
                dimmed && 'opacity-40',
              )}
            >
              <MediaTile item={option} />
              {isCorrect ? <Verdict tone="right" /> : null}
              {isChosenWrong ? <Verdict tone="wrong" /> : null}
            </button>
          )
        })}
      </div>
    </BoardShell>
  )
}

function Verdict({ tone }: { tone: 'right' | 'wrong' }) {
  const right = tone === 'right'
  return (
    <span
      className={cx(
        'animate-pop absolute top-[1.2vh] right-[1.2vh] flex h-[5vh] w-[5vh] items-center justify-center rounded-full text-ink-900',
        right ? 'bg-mint' : 'bg-rose',
      )}
      aria-label={right ? 'correct' : 'not correct'}
    >
      <svg viewBox="0 0 24 24" className="h-[3vh] w-[3vh]" aria-hidden>
        <path
          d={right ? 'M5 13l4 4L19 7' : 'M6 6l12 12M18 6L6 18'}
          fill="none"
          stroke="currentColor"
          strokeWidth="3.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  )
}
