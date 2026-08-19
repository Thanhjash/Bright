/**
 * OverlayLayer — everything that floats above the board and the avatar
 * (docs/design/runtime-topology.md §4): subtitle, student name, listening indicator, mode badge.
 *
 * It is pointer-transparent by construction. Nothing here is ever tapped;
 * the board owns every interaction.
 */
import { ModeBadge } from './ModeBadge'
import { StudentName } from './StudentName'
import { SubtitleBar } from './SubtitleBar'

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

      {/* Bottom lane: BELOW the board, not over it. What she is saying is for
          the class to hear; the chalk is for them to read, and a subtitle
          parked across the foot of the board covers the line she just wrote.
          `--board-bottom` comes from Stage and is measured off the artwork. */}
      <div className="flex flex-col items-center px-[4vw] pb-[2vh] pt-[calc(var(--board-bottom)-64vh)] lg:pr-[calc(var(--avatar-col)+2vw)]">
        <SubtitleBar />
      </div>
    </div>
  )
}
