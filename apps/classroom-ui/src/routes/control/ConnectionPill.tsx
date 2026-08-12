/**
 * Visible but unobtrusive connection state.
 *
 * `/control` always shows it — the person holding the laptop is the one who
 * can do something about it. `/classroom` shows nothing unless disconnected
 * (see stage/DisconnectedNotice.tsx).
 */
import { useClassroom } from '../../store/classroom'
import type { ConnectionState } from '../../bus'

const LOOK: Record<ConnectionState, { label: string; dot: string; text: string }> = {
  open: { label: 'Connected', dot: 'bg-mint', text: 'text-mint' },
  mock: { label: 'Mock data', dot: 'bg-violet', text: 'text-violet' },
  connecting: { label: 'Connecting', dot: 'bg-amber', text: 'text-amber' },
  reconnecting: { label: 'Reconnecting', dot: 'bg-amber', text: 'text-amber' },
  closed: { label: 'Disconnected', dot: 'bg-coral', text: 'text-coral' },
}

export function ConnectionPill() {
  const connection = useClassroom((s) => s.connection)
  const look = LOOK[connection.state]
  const busy = connection.state === 'connecting' || connection.state === 'reconnecting'

  return (
    <span
      className="flex items-center gap-2.5 rounded-full bg-ink-800 px-4 py-2 text-sm font-bold ring-2 ring-ink-600"
      title={connection.lastError ?? look.label}
    >
      <span className="relative flex h-2.5 w-2.5">
        {busy ? (
          <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-70 ${look.dot}`} />
        ) : null}
        <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${look.dot}`} />
      </span>
      <span className={look.text}>{look.label}</span>
      {connection.attempts > 0 ? (
        <span className="text-muted">
          attempt {connection.attempts}
          {connection.retryInMs ? ` · retry in ${Math.round(connection.retryInMs / 100) / 10}s` : ''}
        </span>
      ) : null}
    </span>
  )
}
