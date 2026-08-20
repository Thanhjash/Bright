import type { ChoiceProps } from '@contracts'
import { BoardShell, MediaTile, Prompt, cx } from './parts'

/**
 * `choice` — prompt plus options.
 *
 * A tap emits `interaction.choice { optionId }` and paints a press state
 * immediately. It does NOT decide whether the answer was right: `revealed`
 * arrives on the next `scene.update` and is the only source of truth for the
 * green tick and the red cross.
 */
/**
 * The options, shown. Not tapped.
 *
 * Children in this classroom answer by SPEAKING -- the room is a projector and
 * nobody has a mouse. The tap handler and the hover lift were left over from
 * the deleted lesson-graph player: `currentResponseCorrelation()` is
 * permanently null without a `class.turn.assigned` event that Core no longer
 * publishes, so a tap did nothing at all, silently, while the card rose to meet
 * the finger. An affordance that promises a response it cannot give is worse
 * than no affordance.
 */
export function ChoiceBoard({ props }: { props: ChoiceProps }) {
  const revealed = props.revealed
  const options = props.options ?? []
  /**
   * A card is as large as its content plus a hand's width of padding.
   *
   * Pictures WANT area, so an option with a picture still fills its cell. Words
   * do not: the shipping unit sends two text-only options
   * (`exercises.md`, "How does Mai answer?" / "Fine, thank you." vs "Hello. I'm
   * Mai.") and the full-height stretch turned each into a 443px navy billboard
   * -- 68% of the board -- holding one short sentence. Empty chalk around the
   * group is correct. An inflated card is not "using the space", it is hiding
   * the answer.
   */
  const textOnly = options.length > 0 && options.every((o) => !o.asset)

  return (
    <BoardShell align="stretch" justify={textOnly ? 'center' : 'between'}>
      <Prompt>{props.prompt}</Prompt>

      <div
        className={cx(
          'grid min-h-0 gap-[1.8vw]',
          textOnly
            ? 'mx-auto w-full max-w-[86%] grid-cols-1 auto-rows-min gap-[1.8vh]'
            : cx(
                'flex-1 grid-rows-1',
                options.length >= 4
                  ? 'grid-cols-4'
                  : options.length === 3
                    ? 'grid-cols-3'
                    : 'grid-cols-2',
              ),
        )}
      >
        {options.map((option, i) => {
          const isCorrect = revealed?.correctId === option.id
          const isChosenWrong = revealed?.chosenId === option.id && !isCorrect
          const dimmed = Boolean(revealed) && !isCorrect && !isChosenWrong

          return (
            <div
              key={option.id}
              style={{ animationDelay: `${i * 60}ms` }}
              className={cx(
                'animate-rise card-surface relative flex min-h-0 overflow-hidden',
                textOnly ? 'p-[2.4vh_2vw]' : 'p-[2.2vh_1.2vw]',
                'transition-[transform,box-shadow,background-color,border-color,opacity] duration-200 ease-out',
                isCorrect &&
                  'border-mint bg-mint/18 shadow-[0_0_0_0.7vh_rgba(61,220,151,0.3)] -translate-y-[0.8vh]',
                isChosenWrong && 'border-rose bg-rose/18',
                dimmed && 'opacity-40',
              )}
            >
              <MediaTile item={option} />
              {isCorrect ? <Verdict tone="right" /> : null}
              {isChosenWrong ? <Verdict tone="wrong" /> : null}
            </div>
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
