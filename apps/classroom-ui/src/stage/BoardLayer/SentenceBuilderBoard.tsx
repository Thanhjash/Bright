/**
 * `sentence_builder` — word tiles dragged up onto a sentence line.
 *
 * PROTOCOL.md §2 gives the tokens ids but gives the *positions* none, and §9.4
 * only says a drag grades `toId` or `"fromId>toId"`. So this client names the
 * positions `slot1…slotN`, 1-based, and emits
 *
 *   interaction.drag { fromId: <tokenId>, toId: "slot<n>" }
 *
 * which makes `correct: "t1>slot1"` ("the first word is I") authorable today.
 * Flagged in README as a candidate protocol amendment — no authored lesson
 * grades this scene by drag yet (the example grades it by speech), so nothing
 * depends on the guess.
 *
 * Taking a word back OUT of the sentence deliberately emits nothing. Core
 * enforces one graded answer per activity, and spending the child's single
 * answer on an undo would be indefensible.
 */
import { useEffect, useMemo, useState } from 'react'
import type { SentenceBuilderProps } from '@contracts'
import { useBus } from '../../bus'
import { currentResponseCorrelation } from '../../store/classroom'
import { BoardShell, cx } from './parts'
import { useDragPair } from './useDragPair'

export function SentenceBuilderBoard({ props }: { props: SentenceBuilderProps }) {
  const bus = useBus()
  const tokens = props.tokens ?? []
  const serverPlaced = props.placed ?? []

  const byId = useMemo(() => new Map(tokens.map((t) => [t.id, t.text])), [tokens])
  const signature = useMemo(() => tokens.map((t) => t.id).join(','), [tokens])

  const [local, setLocal] = useState<string[]>([])
  useEffect(() => setLocal([]), [signature])

  /** Server first, then what the child has done since; unknown ids dropped. */
  const placed = useMemo(() => {
    const seen = new Set<string>()
    const out: string[] = []
    for (const id of [...serverPlaced, ...local]) {
      if (seen.has(id) || !byId.has(id)) continue
      seen.add(id)
      out.push(id)
    }
    return out
  }, [serverPlaced, local, byId])

  const tray = tokens.filter((t) => !placed.includes(t.id))
  const nextSlot = `slot${placed.length + 1}`

  const drag = useDragPair({
    onDrop: (fromId, toId) => {
      if (!toId.startsWith('slot') || placed.includes(fromId)) return
      const correlation = currentResponseCorrelation()
      if (!correlation) return
      setLocal((prev) => [...prev, fromId]) // optimistic, same tick as the drop
      bus.send('interaction.drag', { fromId, toId, ...correlation })
    },
  })

  const ghostText = drag.state.dragging ? byId.get(drag.state.activeId ?? '') : undefined
  const over = drag.state.overId === nextSlot

  return (
    <BoardShell align="stretch" justify="between">
      {props.target ? (
        <p className="animate-rise t-board-sm max-w-[95%] self-center text-center font-display font-extrabold text-balance text-cream">
          {props.target}
        </p>
      ) : null}

      {/* ── the sentence line: one big drop zone ─────────────────────── */}
      <div
        {...drag.target(nextSlot)}
        className={cx(
          'flex min-h-[26vh] w-full flex-wrap content-center items-center justify-center gap-[1vh_0.9vw]',
          'rounded-[1.75rem] border-4 border-dashed p-[2vh_1.5vw] transition-colors duration-150',
          over ? 'border-amber bg-amber/12' : 'border-ink-500/70 bg-ink-800/40',
        )}
      >
        {placed.map((id, i) => (
          <button
            key={id}
            type="button"
            onPointerDown={() => setLocal((prev) => prev.filter((p) => p !== id))}
            disabled={serverPlaced.includes(id)}
            style={{ animationDelay: `${i * 40}ms`, touchAction: 'none' }}
            className={cx(
              'animate-pop rounded-[1.1rem] border-3 border-amber bg-amber/22 px-[1.2vw] py-[1.4vh]',
              'font-display text-[clamp(1.6rem,3.1vw,3.4rem)] leading-none font-extrabold text-cream',
              !serverPlaced.includes(id) && 'cursor-pointer hover:bg-amber/32',
            )}
          >
            {byId.get(id)}
          </button>
        ))}

        {/* The next position, always visible so the line reads as unfinished. */}
        {tray.length ? (
          <span
            className={cx(
              'rounded-[1.1rem] border-3 border-dashed px-[2.4vw] py-[1.4vh]',
              'font-display text-[clamp(1.6rem,3.1vw,3.4rem)] leading-none font-extrabold',
              over ? 'border-amber text-amber' : 'animate-breathe border-ink-500 text-ink-500',
            )}
            aria-label="next word goes here"
          >
            &nbsp;
          </span>
        ) : (
          <span className="animate-pop rounded-full bg-mint/20 px-[1.6vw] py-[1.2vh] font-display text-[clamp(1.1rem,2vw,2.1rem)] font-extrabold text-mint">
            All the words are in!
          </span>
        )}
      </div>

      {/* ── the tray ─────────────────────────────────────────────────── */}
      <div className="flex w-full flex-wrap items-center justify-center gap-[1.4vh_1vw]">
        {tray.map((t, i) => {
          const grip = drag.source(t.id)
          const isActive = drag.state.activeId === t.id
          return (
            <div
              key={t.id}
              {...grip}
              role="button"
              style={{ ...grip.style, animationDelay: `${i * 55}ms` }}
              className={cx(
                'animate-rise card-surface cursor-grab px-[1.3vw] py-[1.6vh]',
                'font-display text-[clamp(1.6rem,3.1vw,3.4rem)] leading-none font-extrabold text-cream',
                'transition-[transform,opacity,border-color,background-color] duration-150 ease-out',
                'hover:-translate-y-[0.7vh] hover:border-amber/70',
                isActive && drag.state.dragging && 'scale-[0.94] opacity-30',
                isActive &&
                  drag.state.armed &&
                  'scale-[1.05] border-amber bg-amber/20 shadow-[0_0_0_0.6vh_rgba(255,182,39,0.28)]',
              )}
            >
              {t.text}
            </div>
          )
        })}
      </div>

      {ghostText ? (
        <div
          style={drag.ghostStyle}
          className="card-surface flex items-center justify-center border-amber bg-amber/30 px-[1.3vw] py-[1.6vh] font-display text-[clamp(1.6rem,3.1vw,3.4rem)] leading-none font-extrabold text-cream shadow-2xl"
        >
          {ghostText}
        </div>
      ) : null}
    </BoardShell>
  )
}
