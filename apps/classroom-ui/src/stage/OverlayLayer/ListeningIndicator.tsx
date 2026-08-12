import { selectListening, useClassroom } from '../../store/classroom'

/**
 * "I am listening to you now."
 *
 * Children need to know when it is their turn to speak without anyone
 * explaining the rule, so this is loud, animated, and never subtle.
 */
export function ListeningIndicator() {
  const listening = useClassroom(selectListening)
  if (!listening) return null

  return (
    <div className="animate-pop flex items-center gap-[1.2vw] rounded-full bg-ink-950/80 px-[2vw] py-[1.2vh] ring-3 ring-mint/60 backdrop-blur-sm">
      <span className="flex h-[3.6vh] items-end gap-[0.35vw]">
        {[0, 1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className="w-[0.55vw] min-w-[5px] rounded-full bg-mint"
            style={{
              height: `${[46, 74, 100, 68, 40][i]}%`,
              animation: 'listen 1.1s ease-in-out infinite',
              animationDelay: `${i * 110}ms`,
              transformOrigin: 'bottom',
            }}
          />
        ))}
      </span>
      <span className="font-display text-[clamp(1rem,1.7vw,1.9rem)] font-extrabold tracking-tight text-mint">
        Listening
      </span>
    </div>
  )
}
