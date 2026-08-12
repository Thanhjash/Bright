/** `/control` — setup, quiet supervision and classroom safety. */
import { useCallback, useState } from 'react'
import { BusProvider } from '../../bus'
import { CommandBar } from './CommandBar'
import { ConnectionPill } from './ConnectionPill'
import { LinkHealth } from './LinkHealth'
import { StatusPanel } from './StatusPanel'
import { VoicePanel } from './VoicePanel'
import { SetupPanel } from './SetupPanel'
import { IS_MOCK } from '../../lib/env'
import { mockRoster } from './lessonSetup'
import type { LessonSetup } from './lessonSetup'
import { useClassroom } from '../../store/classroom'

export function ControlRoute() {
  const seeded = IS_MOCK ? mockRoster() : []
  const [setup, setSetupState] = useState<LessonSetup>(() => ({
    lessonId: '',
    classId: '',
    roster: seeded,
    attendanceIds: seeded.map(({ id }) => id),
  }))
  const setSetup = useCallback((next: LessonSetup) => setSetupState(next), [])

  return (
    <BusProvider role="control">
      <div className="flex h-full w-full flex-col overflow-hidden bg-ink-900 text-cream">
        <a href="#control-main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-amber focus:p-3 focus:text-ink-950">
          Skip to classroom controls
        </a>
        <header className="flex shrink-0 items-center justify-between gap-3 border-b-3 border-ink-700 px-5 py-3">
          <div className="flex items-baseline gap-3">
            <span className="font-display text-2xl font-extrabold tracking-tight">Bright</span>
            <span className="rounded-full bg-ink-700 px-3 py-1 text-xs font-bold tracking-[0.16em] text-muted uppercase">Facilitator</span>
          </div>
          <div className="flex items-center gap-3"><LinkHealth /><ConnectionPill /></div>
        </header>

        <main id="control-main" className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(22rem,0.85fr)] lg:overflow-hidden">
          <div className="flex min-h-0 flex-col gap-4 lg:overflow-y-auto">
            <StatusPanel />
            {!useRunningSession() ? <SetupPanel value={setup} onChange={setSetup} /> : null}
            <CommandBar setup={setup} />
          </div>
          <div className="min-h-0 lg:overflow-y-auto"><VoicePanel /></div>
        </main>
      </div>
    </BusProvider>
  )
}

function useRunningSession(): boolean {
  // Kept as a tiny selector component helper so setup disappears during class
  // without duplicating server-derived session rules in local form state.
  const session = useClassroom((state) => state.session)
  return session?.status === 'RUNNING' || session?.status === 'PAUSED' || session?.status === 'RECOVERING'
}
