import { BoardShell } from './parts'

/** `idle` — between activities. Calm, warm, obviously alive, says nothing
 *  a child has to read. */
export function IdleBoard() {
  return (
    <BoardShell>
      <div className="animate-scene-in flex flex-col items-center gap-[3vh]">
        <div className="relative">
          <div className="absolute inset-0 -m-[6vh] rounded-full bg-amber/12 blur-3xl" aria-hidden />
          <svg
            viewBox="0 0 120 120"
            className="relative h-[26vh] w-[26vh] animate-breathe"
            aria-hidden
          >
            <defs>
              <linearGradient id="idle-sun" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#ffd166" />
                <stop offset="1" stopColor="#ff8a5b" />
              </linearGradient>
            </defs>
            {Array.from({ length: 12 }).map((_, i) => (
              <rect
                key={i}
                x="57.5"
                y="4"
                width="5"
                height="16"
                rx="2.5"
                fill="url(#idle-sun)"
                opacity={0.55 + 0.45 * Math.abs(Math.cos((i / 12) * Math.PI))}
                transform={`rotate(${i * 30} 60 60)`}
              />
            ))}
            <circle cx="60" cy="60" r="30" fill="url(#idle-sun)" />
            <circle cx="50" cy="55" r="4" fill="#0a0f2c" />
            <circle cx="70" cy="55" r="4" fill="#0a0f2c" />
            <path
              d="M48 68 Q60 79 72 68"
              stroke="#0a0f2c"
              strokeWidth="4.5"
              strokeLinecap="round"
              fill="none"
            />
          </svg>
        </div>
        <p className="t-board-md font-display font-extrabold tracking-tight text-cream">Ready</p>
      </div>
    </BoardShell>
  )
}
