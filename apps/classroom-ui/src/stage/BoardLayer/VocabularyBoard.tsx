import { useState } from 'react'
import type { MediaItem, VocabularyProps } from '@contracts'
import { useBus } from '../../bus'
import { MediaTile, BoardShell, cx } from './parts'

/**
 * `vocabulary` — the word-card grid.
 *
 * Interaction (PROTOCOL.md §2):
 *  · `none`  → display only, cards are inert
 *  · `point` → a tap emits `interaction.point { targetId, x, y }`
 *  · `tap`   → same event; the protocol defines no separate tap event, and a
 *              tap on a card *is* a point at that card. See README ambiguities.
 *
 * `x`/`y` are normalised 0…1 **within the tapped card**, so they survive any
 * projector resolution. The centre of a card is (0.5, 0.5).
 *
 * The pressed state is local and immediate; `highlightId` is authoritative and
 * arrives on the next `scene.update`.
 */
export function VocabularyBoard({ props }: { props: VocabularyProps }) {
  const bus = useBus()
  const [pressed, setPressed] = useState<string | null>(null)
  const interactive = props.interaction !== 'none'
  const items = props.items ?? []

  function point(item: MediaItem, event: React.PointerEvent<HTMLButtonElement>) {
    if (!interactive) return
    setPressed(item.id) // optimistic, same tick as the tap
    const r = event.currentTarget.getBoundingClientRect()
    const x = r.width ? clamp01((event.clientX - r.left) / r.width) : 0.5
    const y = r.height ? clamp01((event.clientY - r.top) / r.height) : 0.5
    bus.send('interaction.point', { targetId: item.id, x, y })
    window.setTimeout(() => setPressed((p) => (p === item.id ? null : p)), 420)
  }

  return (
    <BoardShell align="stretch">
      <div
        className={cx(
          'grid h-full w-full min-h-0 gap-[2.2vh_1.8vw]',
          gridShape(items.length),
        )}
      >
        {items.map((item, i) => {
          const isHighlight = props.highlightId === item.id
          return (
            <button
              key={item.id}
              type="button"
              disabled={!interactive}
              onPointerDown={(e) => point(item, e)}
              style={{ animationDelay: `${i * 55}ms` }}
              className={cx(
                'animate-rise card-surface relative flex min-h-0 overflow-hidden p-[2.2vh_1.2vw]',
                'transition-[transform,box-shadow,background-color,border-color] duration-200 ease-out',
                interactive && 'cursor-pointer hover:-translate-y-[0.6vh] hover:border-amber/70',
                pressed === item.id && 'scale-[0.95] border-amber bg-amber/20',
                isHighlight &&
                  'border-amber bg-amber/18 shadow-[0_0_0_0.7vh_rgba(255,182,39,0.28)] -translate-y-[0.8vh]',
              )}
            >
              <MediaTile item={item} />
              {isHighlight ? (
                <span className="animate-pop absolute top-[1.2vh] right-[1.2vh] flex h-[4.4vh] w-[4.4vh] items-center justify-center rounded-full bg-amber text-ink-900">
                  <svg viewBox="0 0 24 24" className="h-[2.6vh] w-[2.6vh]" aria-hidden>
                    <path
                      d="M5 13l4 4L19 7"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              ) : null}
            </button>
          )
        })}
      </div>
    </BoardShell>
  )
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, Math.round(n * 1000) / 1000))
}

/** Rows must be declared explicitly: implicit grid rows are auto-sized, which
 *  makes a 2×2 board render one squashed row and one huge one. */
function gridShape(count: number): string {
  if (count <= 1) return 'grid-cols-1 grid-rows-1'
  if (count === 2) return 'grid-cols-2 grid-rows-1'
  if (count === 3) return 'grid-cols-3 grid-rows-1'
  if (count === 4) return 'grid-cols-2 grid-rows-2'
  if (count <= 6) return 'grid-cols-3 grid-rows-2'
  if (count <= 8) return 'grid-cols-4 grid-rows-2'
  return 'grid-cols-4 grid-rows-3'
}
