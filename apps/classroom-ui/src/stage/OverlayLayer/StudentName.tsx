import { selectStudentName, useClassroom } from '../../store/classroom'

/** Whose turn it is. Big enough to read from the back row. */
export function StudentName() {
  const name = useClassroom(selectStudentName)
  if (!name) return <span />

  return (
    <span className="animate-pop flex items-center gap-[0.8vw] rounded-full bg-ink-950/78 py-[0.8vh] pr-[1.6vw] pl-[0.9vw] ring-3 ring-amber/50 backdrop-blur-sm">
      <span className="flex h-[4vh] w-[4vh] items-center justify-center rounded-full bg-amber font-display text-[clamp(0.9rem,1.5vw,1.7rem)] font-extrabold text-ink-900">
        {name.slice(0, 1).toUpperCase()}
      </span>
      <span className="font-display text-[clamp(1rem,1.7vw,1.9rem)] font-extrabold tracking-tight text-cream">
        {name}
      </span>
    </span>
  )
}
