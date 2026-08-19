/**
 * Never a blank screen in front of a class (PROTOCOL.md §2, rule 3).
 *
 * Two failure modes land here: a `scene.kind` this build does not know, and a
 * render that threw.
 *
 * What the ROOM sees is a calm line in the class's own language and nothing
 * else. There is no laptop to stand at: the projector is the only screen the
 * children see, the adult set the appliance up and walked away, and neither of
 * them can act on "protocol v3 vs vundefined". Until 2026-08-19 this card put
 * that sentence, and a raw JSON dump of the scene, on the wall in English in
 * front of thirty Grade-3 children who read neither.
 *
 * The technical detail still exists -- it goes to the console, and the fault
 * itself reaches the adult through /teacher/status, where someone who can act
 * on it is looking.
 */
import { useEffect } from 'react'
import { ROOM_LABELS } from '../../room/labels'
import { BoardShell } from './parts'

export function ErrorCard({
  title,
  detail,
  raw,
}: {
  /** Engineering detail. Console only -- never rendered. */
  title: string
  detail: string
  raw?: unknown
}) {
  useEffect(() => {
    console.error(`[board] ${title}: ${detail}`, raw)
  }, [title, detail, raw])

  const label = ROOM_LABELS.boardFault
  return (
    <BoardShell>
      <div className="animate-scene-in card-surface flex max-h-full w-full max-w-[76%] flex-col items-center gap-[2vh] overflow-hidden border-coral/70 p-[4vh_4vw] text-center">
        <span className="flex h-[8vh] w-[8vh] items-center justify-center rounded-full bg-coral/25">
          <svg viewBox="0 0 24 24" className="h-[4.4vh] w-[4.4vh] text-coral" aria-hidden>
            <path
              d="M12 8v5m0 3.5v.01M12 3l9 16H3l9-16z"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <h2 className="t-board-md font-display font-extrabold text-cream">{label.cta}</h2>
        <p className="t-caption max-w-[44ch] text-muted">{label.sub}</p>
      </div>
    </BoardShell>
  )
}
