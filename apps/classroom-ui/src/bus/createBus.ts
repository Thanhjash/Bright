import { BUS_URL, IS_MOCK } from '../lib/env'
import { useClassroom } from '../store/classroom'
import { MockBus } from './mockClient'
import { WsBus } from './wsClient'
import type { Bus } from './types'

/**
 * The only place that decides mock vs live. Everything downstream sees `Bus`.
 */
export function createBus(role: 'stage' | 'control'): Bus {
  if (IS_MOCK) return new MockBus(role)
  return new WsBus({
    url: BUS_URL,
    role,
    getStateVersion: () => useClassroom.getState().stateVersion,
  })
}
