/**
 * Projector room: photoreal wall, Hermes board in the chalk rect, AIRI body
 * in front. AvatarLayer must not remount when scene.update arrives.
 */
import type { CSSProperties } from 'react'
import { CORE_HTTP } from '../lib/env'
import { SceneRouter } from './SceneRouter'
import { AvatarLayer } from './AvatarLayer/AvatarLayer'
import { OverlayLayer } from './OverlayLayer/OverlayLayer'
import { DisconnectedNotice } from './DisconnectedNotice'
import { useClassroom } from '../store/classroom'
import { ClassroomNotice } from './ClassroomNotice'
import { RoomDock } from './RoomDock'

const WALL = `${CORE_HTTP}/assets/stage/classroom-board.png`

/**
 * The chalk face, measured off the artwork rather than guessed: the green
 * rectangle in `classroom-board.png` runs x 4.7%..90.8%, y 7.8%..87.3%.
 *
 * The width stops well short of that, at 66%, and the gap is deliberate. The
 * right third of the frame is the avatar's column -- she stands in front of the
 * board, and chalk written under her is chalk nobody reads. Everything the
 * SYSTEM says to the adult (the subtitle, the mic warning, the dock) lives in
 * the strip below the board, outside the chalk entirely. The chalk belongs to
 * the child.
 */
const BOARD: CSSProperties = {
  left: '4.7%',
  top: '7.8%',
  width: '66%',
  height: '72%',
}

/** Where the board's bottom edge sits, so chrome can stay under it. */
const BOARD_BOTTOM = '80%'

export function Stage() {
  const scene = useClassroom((s) => s.scene)

  return (
    <main
      className="stage-surface relative h-full w-full overflow-hidden bg-ink-950"
      style={
        { '--avatar-col': '28%', '--board-bottom': BOARD_BOTTOM } as CSSProperties
      }
    >
      <img
        src={WALL}
        alt=""
        data-stage="wall"
        className="pointer-events-none absolute inset-0 h-full w-full object-cover object-left"
      />

      <section
        data-stage="board"
        className="absolute z-10 overflow-hidden"
        style={BOARD}
      >
        <SceneRouter scene={scene} />
      </section>

      <aside
        data-stage="avatar"
        className="absolute bottom-[-4%] right-[1%] z-20 h-[78%] w-[min(30vw,26%)] min-w-[10rem]"
      >
        <AvatarLayer />
      </aside>

      <OverlayLayer />
      <RoomDock />
      <ClassroomNotice />
      <DisconnectedNotice />
    </main>
  )
}
