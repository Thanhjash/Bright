/**
 * `/control` — the facilitator console.
 *
 * Codex ranked "loss of teacher control" as risk #2 for this product
 * (docs/3-design/runtime-topology.md §1). So this screen has exactly one job: let a teacher see what is
 * happening and stop or steer it in one tap, without understanding anything
 * about the system. Every command button is a touch target, always enabled,
 * and always visible without scrolling.
 */
import { BusProvider } from '../../bus'
import { CommandBar } from './CommandBar'
import { ConnectionPill } from './ConnectionPill'
import { LinkHealth } from './LinkHealth'
import { StatusPanel } from './StatusPanel'
import { TranscriptPanel } from './TranscriptPanel'
import { VoicePanel } from './VoicePanel'

export function ControlRoute() {
  return (
    <BusProvider role="control">
      <div className="flex h-full w-full flex-col bg-ink-900 text-cream">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b-3 border-ink-700 px-6 py-4">
          <div className="flex items-baseline gap-3">
            <span className="font-display text-2xl font-extrabold tracking-tight">Bright</span>
            <span className="rounded-full bg-ink-700 px-3 py-1 text-xs font-bold tracking-[0.16em] text-muted uppercase">
              Facilitator
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <LinkHealth />
            <ConnectionPill />
          </div>
        </header>

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-5 p-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          {/* Left: where the lesson is, and the six ways to steer it. */}
          <div className="flex min-h-0 flex-col gap-5 overflow-y-auto">
            <StatusPanel />
            <CommandBar />
          </div>
          {/* Right: the child's voice going in, and everything said coming back.
              Hold-to-talk is held for seconds at a time while a teacher watches
              a child, so it sits ABOVE the fold beside the transcript it feeds —
              not at the bottom of a column that scrolls on a small laptop. */}
          <div className="flex min-h-0 flex-col gap-5">
            <VoicePanel />
            <TranscriptPanel />
          </div>
        </div>
      </div>
    </BusProvider>
  )
}
