/**
 * `explore` — English as a window on the world (north-star §1).
 *
 * This is the one scene that is not a question. Nobody is being tested; a child
 * is being invited to choose what the class looks at next. So it is drawn as a
 * constellation rather than a list: the topic sits in the middle and its nodes
 * orbit it, joined by visible threads, each one a big picture you obviously
 * touch. A list says "here are your options". A constellation says "here is a
 * world, and it is bigger than this screen".
 *
 * The first attempt put the topic in the middle with the nodes in a full ring
 * around it. Screenshotted at 1600×900 it was unusable: a 16:9 board minus the
 * overlay lanes is 1104×621, and four cards big enough to want to touch simply
 * do not fit around a hub in that box — the cards painted straight over the
 * topic and cut its first word off. So the topic moved to the top and the nodes
 * hang below it on an arc. Cards are spaced by division rather than by
 * trigonometry, which makes a collision arithmetically impossible at any
 * resolution; only the *height* varies along the arc, and that has a whole row
 * to play with. Above six nodes an arc gets thin and it falls back to a grid —
 * a crowded constellation is worse than an honest grid.
 *
 * A tap emits `interaction.point { targetId, x, y }` with `x`/`y` normalised
 * 0…1 inside the tapped node (PROTOCOL.md §9.3 — "a tap is a point at that
 * element"; the protocol defines no separate explore event). `focusId` from the
 * next `scene.update` is the authority for what is actually open; the press
 * state below is only the promise that the tap landed.
 */
import { useState } from 'react'
import type { ExploreProps } from '@contracts'
import { useBus } from '../../bus'
import { currentResponseCorrelation } from '../../store/classroom'
import { BoardShell, Picture, cx } from './parts'

type Node = ExploreProps['nodes'][number]

/** Nodes past this count stop fitting on a ring; use a grid instead. */
const ORBIT_MAX = 6

export function ExploreBoard({ props }: { props: ExploreProps }) {
  const bus = useBus()
  const nodes = props.nodes ?? []
  const [pressed, setPressed] = useState<string | null>(null)
  const orbit = nodes.length > 0 && nodes.length <= ORBIT_MAX

  function open(node: Node, button: HTMLButtonElement, clientX?: number, clientY?: number) {
    const correlation = currentResponseCorrelation()
    if (!correlation) return
    setPressed(node.id) // optimistic, same tick as the tap
    const r = button.getBoundingClientRect()
    const x = r.width && clientX !== undefined ? clamp01((clientX - r.left) / r.width) : 0.5
    const y = r.height && clientY !== undefined ? clamp01((clientY - r.top) / r.height) : 0.5
    bus.send('interaction.point', { targetId: node.id, x, y, ...correlation })
    window.setTimeout(() => setPressed((p) => (p === node.id ? null : p)), 420)
  }

  const card = (node: Node, i: number, style?: React.CSSProperties) => (
    <NodeCard
      key={node.id}
      node={node}
      index={i}
      focused={props.focusId === node.id}
      pressed={pressed === node.id}
      onOpen={open}
      style={style}
    />
  )

  if (!orbit) {
    return (
      <BoardShell align="stretch" justify="between">
        <Topic text={props.topic} inline />
        <div
          className={cx(
            'grid min-h-0 w-full flex-1 gap-[2vh_1.4vw]',
            nodes.length <= 8 ? 'grid-cols-4 grid-rows-2' : 'grid-cols-5 grid-rows-2',
          )}
        >
          {nodes.map((n, i) => card(n, i))}
        </div>
      </BoardShell>
    )
  }

  const positions = arc(nodes.length)
  const width = Math.min(22, 92 / nodes.length)

  return (
    <BoardShell align="stretch">
      <div className="flex min-h-0 w-full flex-1 flex-col items-center gap-[1vh]">
        <Topic text={props.topic} inline />

        <div className="relative min-h-0 w-full flex-1">
          {/* Threads from the topic down to each node. `preserveAspectRatio`
              is off so percentages map straight onto the box; the stroke is
              kept uniform by vector-effect. */}
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden
          >
            {positions.map((p, i) => {
              const lit = props.focusId === nodes[i].id
              return (
                <path
                  key={nodes[i].id}
                  d={`M50,0 C50,${p.y * 0.55} ${p.x},${p.y * 0.4} ${p.x},${p.y}`}
                  fill="none"
                  stroke={lit ? '#ffb627' : '#3a4aa0'}
                  strokeWidth={lit ? 5 : 3.5}
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                  opacity={lit ? 0.95 : 0.55}
                />
              )
            })}
          </svg>

          {nodes.map((n, i) =>
            card(n, i, {
              position: 'absolute',
              left: `${positions[i].x}%`,
              top: `${positions[i].y}%`,
              width: `${width}%`,
              transform: 'translate(-50%, 0)',
            }),
          )}
        </div>
      </div>
    </BoardShell>
  )
}

/**
 * Node anchors in container percent: evenly divided horizontally, hung on a
 * shallow dome vertically. Horizontal spacing is division, not trigonometry,
 * so two cards can never land on top of each other however many there are.
 */
function arc(count: number): Array<{ x: number; y: number }> {
  const TOP = 6      // % below the topic where the highest card hangs
  const DROP = 13    // % further down the outermost cards fall
  return Array.from({ length: count }, (_, i) => {
    const x = ((i + 0.5) / count) * 100
    // -1 at the left edge, 0 in the middle, +1 at the right edge.
    const t = count === 1 ? 0 : (i / (count - 1)) * 2 - 1
    return { x, y: TOP + DROP * t * t }
  })
}

function Topic({ text, inline = false }: { text: string; inline?: boolean }) {
  return (
    <div
      className={cx(
        'animate-pop flex items-center justify-center rounded-full text-center',
        'border-4 border-amber/70 bg-ink-900/92 shadow-[0_0_0_1.2vh_rgba(255,182,39,0.12)]',
        inline ? 'px-[2vw] py-[1.2vh]' : 'max-w-[26vw] px-[2.2vw] py-[2.2vh]',
      )}
    >
      <span className="font-display text-[clamp(1.3rem,2.6vw,2.8rem)] leading-tight font-extrabold text-balance text-cream">
        {text}
      </span>
    </div>
  )
}

function NodeCard({
  node,
  index,
  focused,
  pressed,
  onOpen,
  style,
}: {
  node: Node
  index: number
  focused: boolean
  pressed: boolean
  onOpen: (node: Node, button: HTMLButtonElement, clientX?: number, clientY?: number) => void
  style?: React.CSSProperties
}) {
  return (
    <button
      type="button"
      onPointerDown={(e) => onOpen(node, e.currentTarget, e.clientX, e.clientY)}
      onKeyDown={(event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        onOpen(node, event.currentTarget)
      }}
      style={{ ...style, animationDelay: `${index * 80}ms`, touchAction: 'none' }}
      className={cx(
        'animate-rise card-surface group z-20 flex cursor-pointer flex-col items-center gap-[0.9vh] overflow-hidden p-[1.2vh_0.7vw]',
        'transition-[transform,box-shadow,border-color,background-color] duration-200 ease-out',
        'hover:-translate-y-[0.8vh] hover:border-amber/70',
        focused &&
          'border-amber bg-amber/16 shadow-[0_0_0_0.7vh_rgba(255,182,39,0.3)] scale-[1.06]',
        pressed && 'scale-[0.95] border-amber bg-amber/24',
      )}
    >
      <Picture
        asset={node.asset}
        fit="cover"
        className="aspect-[4/3] w-full rounded-[1.1rem]"
      />
      <span className="text-center font-display text-[clamp(1.05rem,2vw,2.2rem)] leading-none font-extrabold tracking-tight text-cream">
        {node.label}
      </span>
    </button>
  )
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, Math.round(n * 1000) / 1000))
}
