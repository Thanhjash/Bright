/**
 * Creates the bus for a route, wires it to the store, and hands it down.
 *
 * `/classroom` mounts it with role `stage`, `/control` with role `control`.
 * In practice these are two browser windows on an extended display, so one
 * bus per page is the whole story.
 */
import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { IS_MOCK } from '../lib/env'
import { useClassroom } from '../store/classroom'
import { createBus } from './createBus'
import { connectBusToStore } from './wiring'
import {
  capabilityReport,
  setLocalCapabilities,
  subscribeLocalCapabilities,
} from './clientCapabilities'
import type { Bus } from './types'

const BusContext = createContext<Bus | null>(null)

export function BusProvider({
  role,
  children,
}: {
  role: 'stage' | 'control'
  children: ReactNode
}) {
  const [bus] = useState(() => createBus(role))

  useEffect(() => {
    // Symmetric: connect on mount, close on unmount. Both implementations
    // support connect-after-close, so StrictMode's double-mount in development
    // just churns one connection, and navigating between the two routes in a
    // single window never leaves an orphaned socket or timer behind.
    const unwire = connectBusToStore(bus)
    setLocalCapabilities(role === 'stage'
      ? {
          stage_link: false,
          // Technical capability only; the room preflight still asks the
          // facilitator to verify the physical speaker/display path.
          audio_output: typeof Audio !== 'undefined',
          display: typeof screen !== 'undefined' && screen.width > 0,
        }
      : { control_link: false, microphone: IS_MOCK })
    const report = () => {
      const connected = bus.status().state === 'open' || bus.status().state === 'mock'
      setLocalCapabilities(role === 'stage' ? { stage_link: connected } : { control_link: connected })
      if (connected)
        bus.send('capability.report', capabilityReport(role))
    }
    const unstatus = bus.onStatus(report)
    const uncap = subscribeLocalCapabilities(report)
    const heartbeat = window.setInterval(report, 4_000)
    useClassroom
      .getState()
      .log('system', IS_MOCK ? 'mock mode — no backend' : `connecting as ${role}`)
    bus.connect()
    return () => {
      unwire()
      unstatus()
      uncap()
      window.clearInterval(heartbeat)
      bus.close()
    }
  }, [bus, role])

  return <BusContext.Provider value={bus}>{children}</BusContext.Provider>
}

export function useBus(): Bus {
  const bus = useContext(BusContext)
  if (!bus) throw new Error('useBus() must be used inside <BusProvider>')
  return bus
}
