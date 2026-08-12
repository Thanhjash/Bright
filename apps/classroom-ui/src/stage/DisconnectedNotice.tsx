/**
 * On /classroom the connection is invisible — until it is broken.
 *
 * Thirty children do not need to see a green dot, but a frozen board with no
 * explanation is the worst thing that can happen in front of a class. So:
 * nothing at all while healthy, and one calm line the moment we drop.
 */
import { useClassroom } from '../store/classroom'

export function DisconnectedNotice() {
  const state = useClassroom((s) => s.connection.state)
  const attempts = useClassroom((s) => s.connection.attempts)

  // 'open' and 'mock' are healthy; a first 'connecting' is not worth a banner.
  if (state === 'open' || state === 'mock') return null
  if (state === 'connecting' && attempts === 0) return null

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 flex justify-center p-[2vh]">
      <div className="animate-pop flex items-center gap-[1vw] rounded-full bg-ink-950/92 px-[2vw] py-[1.2vh] ring-3 ring-coral/60 backdrop-blur">
        <span className="relative flex h-[1.6vh] w-[1.6vh] min-h-[10px] min-w-[10px]">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-coral opacity-70" />
          <span className="relative inline-flex h-full w-full rounded-full bg-coral" />
        </span>
        <span className="font-display text-[clamp(1rem,1.6vw,1.7rem)] font-bold text-cream">
          {state === 'closed'
            ? 'Classroom disconnected'
            : `Reconnecting to the classroom…${attempts > 3 ? ` (${attempts})` : ''}`}
        </span>
      </div>
    </div>
  )
}
