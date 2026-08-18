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

const WALL = `${CORE_HTTP}/assets/stage/classroom-wall.jpg`

/** Chalk face in classroom-wall.jpg (percent of the photo). */
const BOARD: CSSProperties = {
  left: '8.5%',
  top: '10.5%',
  width: '62%',
  height: '67%',
}

export function Stage() {
  const scene = useClassroom((s) => s.scene)

  return (
    <main
      className="stage-surface relative h-full w-full overflow-hidden bg-ink-950"
      style={{ '--avatar-col': '28%' } as CSSProperties}
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
