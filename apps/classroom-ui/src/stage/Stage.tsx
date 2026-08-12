/**
 * The Stage — what the projector shows.
 *
 * Layout (docs/3-design/runtime-topology.md §4): the board takes the majority of
 * the screen, the avatar sits beside it, and the overlay floats above both. On a
 * 16:9 projector that is 75 / 25. Below 1024px wide (a dev laptop, never a
 * classroom) the avatar drops to a strip so the board keeps its size.
 *
 * WHY 25% AND NOT LESS. `fitModel` normalises the model against whichever axis
 * binds first. In a column this narrow that is always width, so the avatar's
 * on-screen size is set by the COLUMN WIDTH, not by the stage height: taking
 * width away from the avatar to give it to the board shrinks her face. Measured
 * on Hiyori Pro (intrinsic 2976×4175) at 1600×900: a 25% column renders her
 * 1010px tall — a 180px head, readable at 8 m. Going to 20% would buy the board
 * five points of width and cost her a fifth of her face. 25% is the floor.
 *
 * `--avatar-col` is declared here and consumed by BOTH the grid and the
 * overlay's subtitle lane, so the subtitle can never drift over the avatar
 * because someone retuned one of the two numbers.
 */
import type { CSSProperties } from 'react'
import { SceneRouter } from './SceneRouter'
import { AvatarLayer } from './AvatarLayer/AvatarLayer'
import { OverlayLayer } from './OverlayLayer/OverlayLayer'
import { DisconnectedNotice } from './DisconnectedNotice'
import { useClassroom } from '../store/classroom'

export function Stage() {
  const scene = useClassroom((s) => s.scene)

  return (
    <main
      className="stage-surface relative h-full w-full overflow-hidden bg-ink-900"
      style={{ '--avatar-col': '25%' } as CSSProperties}
    >
      {/* Ground: a warm vignette, so a projected black never looks like a dead
          signal and the board edges stay visible in a lit room. */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(120% 90% at 50% 0%, #1b2760 0%, #0a0f2c 55%, #05081c 100%)',
        }}
        aria-hidden
      />

      <div className="relative z-10 grid h-full w-full grid-cols-1 grid-rows-[1fr_26vh] lg:grid-cols-[1fr_var(--avatar-col)] lg:grid-rows-1">
        <section data-stage="board" className="relative min-h-0 min-w-0">
          <SceneRouter scene={scene} />
        </section>
        <aside
          data-stage="avatar"
          className="relative min-h-0 min-w-0 border-t-3 border-ink-700/70 lg:border-t-0 lg:border-l-3"
        >
          <AvatarLayer />
        </aside>
      </div>

      <OverlayLayer />
      <DisconnectedNotice />
    </main>
  )
}
