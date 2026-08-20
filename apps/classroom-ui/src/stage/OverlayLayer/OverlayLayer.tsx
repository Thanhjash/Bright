/**
 * OverlayLayer — everything that floats above the board and the avatar
 * (docs/design/runtime-topology.md §4): student name, mode badge.
 *
 * It is pointer-transparent by construction. Nothing here is ever tapped;
 * the board owns every interaction.
 *
 * The subtitle used to have its own bottom lane here, independently
 * bottom-anchored to the viewport -- and so did `RoomDock`'s status pill, in
 * its own independently bottom-anchored strip. Two elements each claiming
 * "the bottom of the screen" as their own is exactly how they ended up
 * printed on top of each other. The subtitle now renders inside `RoomDock`,
 * as one flex column with the status dock and the heard-echo chip, so the
 * three stack instead of collide. See `RoomDock.tsx`.
 */
import { ModeBadge } from './ModeBadge'
import { StudentName } from './StudentName'

export function OverlayLayer() {
  return (
    <div className="pointer-events-none absolute inset-0 z-20 flex flex-col justify-between">
      {/* Top lane, in the AVATAR'S COLUMN only. The new chalkboard art starts
          at 4.7% from the left, so the old full-width top lane sat squarely on
          the chalk: a name chip parked over the first line the teacher writes.
          Pushed right of the board's edge, where the wall is. */}
      <div className="flex items-start justify-end gap-6 p-[2.4vh_2.4vw] pl-[68%]">
        <div className="flex flex-wrap items-center justify-end gap-[1vw]">
          <StudentName />
        </div>
        {/* Renders only in DEGRADED or OFFLINE. It was written and then never
            mounted, so the room could silently lose capability mid-lesson with
            nothing on screen to say so -- a papered-over failure, which the
            failure doctrine calls a defect, not a kindness. */}
        <ModeBadge />
        {/* Provider/model mode is facilitator information, not a child-facing
            failure. Classroom capability recovery is shown separately. */}
      </div>
    </div>
  )
}
