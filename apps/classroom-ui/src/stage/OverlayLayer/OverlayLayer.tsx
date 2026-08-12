/**
 * OverlayLayer — everything that floats above the board and the avatar
 * (docs/3-design/runtime-topology.md §4): subtitle, student name, listening indicator, mode badge.
 *
 * It is pointer-transparent by construction. Nothing here is ever tapped;
 * the board owns every interaction.
 */
import { ListeningIndicator } from './ListeningIndicator'
import { ModeBadge } from './ModeBadge'
import { StudentName } from './StudentName'
import { SubtitleBar } from './SubtitleBar'

export function OverlayLayer() {
  return (
    <div className="pointer-events-none absolute inset-0 z-20 flex flex-col justify-between">
      {/* Top lane: who is up, and whether we are hearing them. Kept away from
          the subtitle so neither can ever cover the board's bottom row. */}
      <div className="flex items-start justify-between gap-6 p-[2.4vh_2.4vw]">
        <div className="flex flex-wrap items-center gap-[1vw]">
          <StudentName />
          <ListeningIndicator />
        </div>
        <ModeBadge />
      </div>

      {/* Bottom lane: subtitles only, and only over the BOARD. `--avatar-col`
          is the same variable the Stage grid uses, so the subtitle cannot creep
          onto the avatar if the split is ever retuned. BoardShell reserves the
          matching height. */}
      <div className="flex flex-col items-center p-[0_4vw_2.5vh] lg:pr-[calc(var(--avatar-col)+2vw)]">
        <SubtitleBar />
      </div>
    </div>
  )
}
