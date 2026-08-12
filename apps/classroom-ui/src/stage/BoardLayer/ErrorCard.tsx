/**
 * Never a blank screen in front of a class (PROTOCOL.md §2, rule 3).
 *
 * Two failure modes land here: a `scene.kind` this build does not know, and a
 * render that threw. Both show something calm and non-alarming to the room,
 * plus enough detail for whoever is standing at the laptop.
 */
import { BoardShell } from './parts'

export function ErrorCard({
  title,
  detail,
  raw,
}: {
  title: string
  detail: string
  raw?: unknown
}) {
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
        <h2 className="t-board-md font-display font-extrabold text-cream">{title}</h2>
        <p className="t-caption max-w-[44ch] text-muted">{detail}</p>
        {raw !== undefined ? (
          <pre className="max-h-[24vh] w-full overflow-auto rounded-2xl bg-ink-900/70 p-[2vh_2vw] text-left font-mono text-[clamp(0.8rem,1vw,1rem)] leading-relaxed text-muted">
            {safeStringify(raw)}
          </pre>
        ) : null}
      </div>
    </BoardShell>
  )
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? String(value)
  } catch {
    return String(value)
  }
}
