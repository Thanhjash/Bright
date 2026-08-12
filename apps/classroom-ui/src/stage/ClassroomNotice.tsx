import { useClassroom } from '../store/classroom'

/** Calm child-facing recovery; technical details remain on Control. */
export function ClassroomNotice() {
  const session = useClassroom((state) => state.session)
  const recovery = useClassroom((state) => state.recovery)

  if (!recovery && session?.status !== 'RECOVERING' && session?.status !== 'PAUSED') return null

  return (
    <div className="pointer-events-none absolute inset-0 z-25 flex items-center justify-center bg-ink-950/60 p-[6vw] backdrop-blur-sm">
      <div className="max-w-[70vw] rounded-[2.5rem] bg-ink-900/96 px-[5vw] py-[5vh] text-center ring-4 ring-amber/55">
        <p className="font-display text-[clamp(2rem,4vw,4.5rem)] font-extrabold text-cream">
          One moment, everyone
        </p>
        <p className="mt-[2vh] text-[clamp(1.2rem,2vw,2.2rem)] text-muted">
          Bright has paused safely. Please stay with your group.
        </p>
      </div>
    </div>
  )
}

