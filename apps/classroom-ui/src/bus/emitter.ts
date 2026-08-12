/** Minimal typed emitter shared by both bus implementations. */
import type { Event } from '@contracts'
import type {
  ConnectionStatus,
  ServerEventType,
  ServerHandler,
  Unsubscribe,
} from './types'

type AnyHandler = (event: Event<unknown>) => void
type StatusHandler = (status: ConnectionStatus) => void
type ResetHandler = (reason: string) => void

export class BusEmitter {
  #typed = new Map<ServerEventType, Set<(p: never, e: Event<never>) => void>>()
  #any = new Set<AnyHandler>()
  #status = new Set<StatusHandler>()
  #reset = new Set<ResetHandler>()

  on<K extends ServerEventType>(type: K, handler: ServerHandler<K>): Unsubscribe {
    let set = this.#typed.get(type)
    if (!set) {
      set = new Set()
      this.#typed.set(type, set)
    }
    const fn = handler as unknown as (p: never, e: Event<never>) => void
    set.add(fn)
    return () => set.delete(fn)
  }

  onAny(handler: AnyHandler): Unsubscribe {
    this.#any.add(handler)
    return () => this.#any.delete(handler)
  }

  onStatus(handler: StatusHandler): Unsubscribe {
    this.#status.add(handler)
    return () => this.#status.delete(handler)
  }

  emit(event: Event<unknown>): void {
    const set = this.#typed.get(event.type as ServerEventType)
    if (set) {
      for (const fn of [...set]) {
        try {
          ;(fn as (p: unknown, e: Event<unknown>) => void)(event.payload, event)
        } catch (err) {
          console.error('[bus] handler threw for', event.type, err)
        }
      }
    }
    for (const fn of [...this.#any]) {
      try {
        fn(event)
      } catch (err) {
        console.error('[bus] onAny handler threw', err)
      }
    }
  }

  onReset(handler: ResetHandler): Unsubscribe {
    this.#reset.add(handler)
    return () => this.#reset.delete(handler)
  }

  emitStatus(status: ConnectionStatus): void {
    for (const fn of [...this.#status]) fn(status)
  }

  emitReset(reason: string): void {
    for (const fn of [...this.#reset]) fn(reason)
  }
}
