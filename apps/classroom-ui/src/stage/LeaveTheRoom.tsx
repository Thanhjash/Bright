/**
 * The way out. A door, not a lesson control.
 *
 * `room-runs-itself` deleted `Start class` and `Hold-to-talk` because they put
 * an adult inside the TEACHING loop — a hand on each turn. Leaving a room is
 * the same act as entering one, across the same boundary the front door already
 * established (`docs/decisions/2026-08-21-the-front-door.md`), so this sits on
 * the outside of that line.
 *
 * It is wired to nothing. It navigates, and that is all:
 *
 *  · no HTTP call, no session change. `say(closing=true)` stays the only
 *    proper end of a period, and it is hers.
 *  · unmounting the bus drops the stage lease by itself, and Core's pulse now
 *    refuses to spend a turn without one — so she does not teach an empty room.
 *  · the session stays open on purpose. A child who steps out and comes back
 *    re-attaches to the SAME period (`resume_teacher_session`, 2h window)
 *    rather than starting the lesson again.
 *
 * If anyone ever proposes making this "say goodbye for her", refuse: that puts
 * a hand on `close_period`, which is the thing the doctrine is about.
 */
import { useNavigate } from 'react-router'
import { LEAVE_LABEL } from '../room/labels'

export function LeaveTheRoom() {
  const navigate = useNavigate()
  return (
    <button
      type="button"
      data-stage="leave"
      aria-label={LEAVE_LABEL}
      onClick={() => navigate('/')}
      className="absolute top-[2.5%] left-[1.4%] z-30 flex items-center gap-2 rounded-2xl bg-ink-900/70 px-4 py-3 text-cream backdrop-blur-sm transition hover:bg-ink-800"
    >
      <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden>
        <path
          d="M14 5H6v14h8M10 12h10m0 0-3.2-3.2M20 12l-3.2 3.2"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="font-display text-base font-extrabold">{LEAVE_LABEL}</span>
    </button>
  )
}
