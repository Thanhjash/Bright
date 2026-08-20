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
import { StudentCamera } from './StudentCamera'

const WALL = `${CORE_HTTP}/assets/stage/classroom-board.png`

/**
 * The chalk face, measured off the artwork rather than guessed: the green
 * rectangle in `classroom-board.png` runs x 4.7%..90.8%, y 7.8%..87.3%.
 *
 * Neither dimension uses the full measured rectangle, and both gaps are
 * deliberate, the same way and for the same reason:
 *
 *   · width stops at 66% (not 90.8%) so the right third of the frame is the
 *     avatar's column -- she stands in front of the board, and chalk written
 *     under her is chalk nobody reads.
 *   · height stops at 60% (not 79.5%) so there is a real strip below the
 *     board for everything the SYSTEM says: the subtitle, the status dock,
 *     the student's own camera corner. That strip used to be a thin 20% band
 *     the subtitle and the status pill both fought over and lost -- text
 *     bled out from under the pill, and the heard-echo chip had nowhere of
 *     its own to live. A shorter board buys the room the strip needs.
 *
 * Both gaps render onto real chalk that was already drawn, never onto wall.
 * The chalk belongs to the child; the strip below it belongs to the room.
 */
const BOARD: CSSProperties = {
  left: '4.7%',
  top: '7.8%',
  width: '66%',
  height: '60%',
}

/** Where the board's bottom edge sits, so chrome can stay under it. */
const BOARD_BOTTOM = '68%'

export function Stage() {
  const scene = useClassroom((s) => s.scene)

  return (
    <main
      className="stage-surface relative h-full w-full overflow-hidden bg-ink-950"
      style={
        {
          '--avatar-col': '28%',
          '--camera-col': '17%',
          '--board-bottom': BOARD_BOTTOM,
        } as CSSProperties
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

      {/* The child's own corner -- opposite the avatar's, and entirely below
          the board's bottom edge, so it never competes with the avatar's
          column or the chalk above it. */}
      <aside
        data-stage="camera-slot"
        className="absolute bottom-[2%] left-[1.4%] z-20 h-[26%] w-[min(15vw,13%)] min-w-[6.5rem]"
      >
        <StudentCamera />
      </aside>

      <OverlayLayer />
      <RoomDock />
      <ClassroomNotice />
      <DisconnectedNotice />
    </main>
  )
}
