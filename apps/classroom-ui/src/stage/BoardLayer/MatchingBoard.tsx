/**
 * `matching` — two columns, dragged together.
 *
 * Wire semantics (PROTOCOL.md §2, §9.4, and the authored example at
 * content/lessons/example/format-example.md → `match_pairs`):
 *
 *   expect: { kind: drag, correct: "apple>an_apple" }
 *
 * i.e. the pair form is **left>right**. So however the child gestures — a
 * picture dragged onto a word, or a word dragged onto a picture — the emitted
 * `interaction.drag` is always normalised to `{ fromId: <left>, toId: <right> }`.
 * The gesture direction is an affordance; the pair is the answer. Core grades
 * `toId` or `fromId>toId` and either works with that normalisation.
 *
 * Core does not send back an updated `solved[]` (it re-publishes the scene to
 * move `stateVersion` and nothing more), so the joined pair is painted from
 * local optimistic state *merged with* `props.solved`. `props.solved` always
 * wins, and a new set of items throws the local state away.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { MatchingProps, MediaItem } from '@contracts'
import { useBus } from '../../bus'
import { BoardShell, MediaTile, cx } from './parts'
import { useDragPair } from './useDragPair'

/** Pair colours, in order. A matched pair shares one, on both sides. */
const PAIR_TONE = [
  { ring: 'border-amber', fill: 'bg-amber/18', dot: 'bg-amber', line: '#ffb627' },
  { ring: 'border-sky', fill: 'bg-sky/18', dot: 'bg-sky', line: '#56ccf2' },
  { ring: 'border-mint', fill: 'bg-mint/18', dot: 'bg-mint', line: '#3ddc97' },
  { ring: 'border-violet', fill: 'bg-violet/18', dot: 'bg-violet', line: '#a88bfa' },
  { ring: 'border-coral', fill: 'bg-coral/18', dot: 'bg-coral', line: '#ff7a59' },
  { ring: 'border-rose', fill: 'bg-rose/18', dot: 'bg-rose', line: '#ff5c7a' },
]

interface Line {
  key: string
  x1: number
  y1: number
  x2: number
  y2: number
  colour: string
}

export function MatchingBoard({ props }: { props: MatchingProps }) {
  const bus = useBus()
  const left = props.left ?? []
  const right = props.right ?? []
  const serverSolved = props.solved ?? []

  const leftIds = useMemo(() => new Set(left.map((i) => i.id)), [left])
  // Identity of *this* exercise. When it changes, optimistic state is stale.
  const signature = useMemo(
    () => [...left.map((i) => i.id), '|', ...right.map((i) => i.id)].join(','),
    [left, right],
  )

  const [local, setLocal] = useState<Array<[string, string]>>([])
  useEffect(() => setLocal([]), [signature])

  /** Server pairs first, then anything the child has done since. */
  const pairs = useMemo(() => {
    const seen = new Set<string>()
    const out: Array<[string, string]> = []
    for (const [l, r] of [...serverSolved, ...local]) {
      if (seen.has(l) || seen.has(r)) continue
      seen.add(l)
      seen.add(r)
      out.push([l, r])
    }
    return out
  }, [serverSolved, local])

  const toneOf = useMemo(() => {
    const map = new Map<string, number>()
    pairs.forEach(([l, r], i) => {
      map.set(l, i % PAIR_TONE.length)
      map.set(r, i % PAIR_TONE.length)
    })
    return map
  }, [pairs])

  const matched = useMemo(() => new Set(pairs.flat()), [pairs])

  const drag = useDragPair({
    isLocked: (id) => matched.has(id),
    canDrop: (fromId, toId) => leftIds.has(fromId) !== leftIds.has(toId),
    onDrop: (fromId, toId) => {
      // Normalise to left>right regardless of which way the child dragged.
      const [l, r] = leftIds.has(fromId) ? [fromId, toId] : [toId, fromId]
      if (matched.has(l) || matched.has(r)) return
      setLocal((prev) => [...prev, [l, r]]) // optimistic, same tick as the drop
      bus.send('interaction.drag', { fromId: l, toId: r })
    },
  })

  // ── connector lines ──────────────────────────────────────────────────
  const frame = useRef<HTMLDivElement | null>(null)
  const cards = useRef(new Map<string, HTMLElement>())
  const [lines, setLines] = useState<Line[]>([])

  useLayoutEffect(() => {
    const box = frame.current
    if (!box) return
    function measure() {
      const host = frame.current
      if (!host) return
      const o = host.getBoundingClientRect()
      const next: Line[] = []
      pairs.forEach(([l, r], i) => {
        const a = cards.current.get(l)
        const b = cards.current.get(r)
        if (!a || !b) return
        const ra = a.getBoundingClientRect()
        const rb = b.getBoundingClientRect()
        next.push({
          key: `${l}>${r}`,
          x1: ra.right - o.left,
          y1: ra.top + ra.height / 2 - o.top,
          x2: rb.left - o.left,
          y2: rb.top + rb.height / 2 - o.top,
          colour: PAIR_TONE[i % PAIR_TONE.length].line,
        })
      })
      setLines(next)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(box)
    return () => ro.disconnect()
  }, [pairs, signature])

  const ghost = drag.state.dragging ? [...left, ...right].find((i) => i.id === drag.state.activeId) : undefined

  function register(id: string) {
    return (el: HTMLElement | null) => {
      if (el) cards.current.set(id, el)
      else cards.current.delete(id)
    }
  }

  return (
    <BoardShell align="stretch">
      <div ref={frame} className="relative grid min-h-0 w-full flex-1 grid-cols-[1fr_8vw_1fr] gap-y-[2vh]">
        {/* Joined pairs, drawn across the gutter. Behind the cards. */}
        <svg className="pointer-events-none absolute inset-0 z-0 h-full w-full" aria-hidden>
          {lines.map((l) => (
            <g key={l.key}>
              <path
                d={`M${l.x1},${l.y1} C${l.x1 + (l.x2 - l.x1) * 0.45},${l.y1} ${l.x1 + (l.x2 - l.x1) * 0.55},${l.y2} ${l.x2},${l.y2}`}
                fill="none"
                stroke={l.colour}
                strokeWidth={7}
                strokeLinecap="round"
                opacity={0.85}
              />
              <circle cx={l.x1} cy={l.y1} r={9} fill={l.colour} />
              <circle cx={l.x2} cy={l.y2} r={9} fill={l.colour} />
            </g>
          ))}
        </svg>

        <Column
          items={left}
          side="left"
          drag={drag}
          toneOf={toneOf}
          matched={matched}
          register={register}
        />
        <div aria-hidden />
        <Column
          items={right}
          side="right"
          drag={drag}
          toneOf={toneOf}
          matched={matched}
          register={register}
        />
      </div>

      {ghost ? (
        <div style={drag.ghostStyle} className="card-surface border-amber bg-amber/25 overflow-hidden p-[1.4vh_0.8vw] opacity-95 shadow-2xl">
          <MediaTile item={ghost} />
        </div>
      ) : null}
    </BoardShell>
  )
}

function Column({
  items,
  side,
  drag,
  toneOf,
  matched,
  register,
}: {
  items: MediaItem[]
  side: 'left' | 'right'
  drag: ReturnType<typeof useDragPair>
  toneOf: Map<string, number>
  matched: Set<string>
  register: (id: string) => (el: HTMLElement | null) => void
}) {
  return (
    <div className="z-10 flex min-h-0 flex-col justify-around gap-[1.8vh]">
      {items.map((item, i) => {
        const tone = toneOf.get(item.id)
        const isMatched = matched.has(item.id)
        const isOver = drag.state.overId === item.id && drag.state.activeId !== item.id
        const isActive = drag.state.activeId === item.id
        const grip = drag.source(item.id)
        return (
          <div
            key={item.id}
            ref={register(item.id)}
            // A matched card is inert: it is neither a handle nor a target.
            {...(isMatched ? {} : drag.target(item.id))}
            {...(isMatched ? {} : { 'data-drag-id': grip['data-drag-id'], onPointerDown: grip.onPointerDown })}
            style={{ ...grip.style, animationDelay: `${i * 60}ms` }}
            className={cx(
              'animate-rise card-surface relative flex min-h-0 flex-1 overflow-hidden p-[1.4vh_0.8vw]',
              'transition-[transform,box-shadow,background-color,border-color,opacity] duration-150 ease-out',
              side === 'left' ? 'mr-[0.6vw]' : 'ml-[0.6vw]',
              !isMatched && 'cursor-grab hover:-translate-y-[0.5vh] hover:border-cream/50',
              isActive && drag.state.dragging && 'scale-[0.96] opacity-35',
              isActive && drag.state.armed && 'scale-[1.03] border-cream shadow-[0_0_0_0.6vh_rgba(251,247,239,0.25)]',
              isOver && 'scale-[1.04] border-cream bg-cream/12',
              tone !== undefined && `${PAIR_TONE[tone].ring} ${PAIR_TONE[tone].fill}`,
            )}
          >
            <MediaTile item={item} />
            {tone !== undefined ? (
              <span
                className={cx(
                  'animate-pop absolute top-[1vh] flex h-[3.6vh] w-[3.6vh] min-h-[22px] min-w-[22px] items-center justify-center rounded-full text-ink-900',
                  side === 'left' ? 'right-[0.6vw]' : 'left-[0.6vw]',
                  PAIR_TONE[tone].dot,
                )}
                aria-label="matched"
              >
                <svg viewBox="0 0 24 24" className="h-[2.2vh] w-[2.2vh] min-h-[13px] min-w-[13px]" aria-hidden>
                  <path
                    d="M5 13l4 4L19 7"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
