import type { CapabilityReportPayload } from '@contracts'

export const CLIENT_INSTANCE_ID = crypto.randomUUID()

let connectionEpoch = 0
const capabilities: Record<string, boolean | string | number> = {}
const listeners = new Set<() => void>()

export function beginConnectionEpoch(): number {
  connectionEpoch += 1
  return connectionEpoch
}

export function currentConnectionEpoch(): number {
  return connectionEpoch
}

export function setLocalCapabilities(next: Record<string, boolean | string | number>): void {
  let changed = false
  for (const [key, value] of Object.entries(next)) {
    if (capabilities[key] === value) continue
    capabilities[key] = value
    changed = true
  }
  if (changed)
    for (const listener of listeners) listener()
}

export function capabilityReport(role: 'stage' | 'control'): CapabilityReportPayload {
  return {
    clientInstanceId: CLIENT_INSTANCE_ID,
    connectionEpoch,
    role,
    capabilities: { ...capabilities },
    reportedAt: Date.now(),
  }
}

export function localCapabilities(): Readonly<Record<string, boolean | string | number>> {
  return { ...capabilities }
}

export function subscribeLocalCapabilities(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
