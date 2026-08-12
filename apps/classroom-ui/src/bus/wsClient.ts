/**
 * WebSocket client for the classroom-core event bus — PROTOCOL.md §1.
 *
 * Three rules drive everything in this file:
 *
 *  1. Every message on the bus is a full `Event<T>` envelope. No exceptions,
 *     including the ones we send.
 *  2. `seq` is monotonic *per connection*. A gap means we missed something,
 *     and we must never patch across it: we throw local state away and take a
 *     fresh snapshot instead.
 *  3. An unknown `v` is rejected loudly. We do not guess.
 *
 * And one rule that is not about correctness but about a classroom — §9.8:
 *
 *  4. Silence is a failure. The transport will not tell us in time (measured:
 *     32 s of `readyState === OPEN` over a black-holed link, and forever if the
 *     FIN is lost too), so the application layer proves liveness itself. No
 *     frame of any kind for 12 s and we declare the link dead ourselves.
 */
import { PROTOCOL_VERSION } from '@contracts'
import type { Event, HeartbeatPayload } from '@contracts'
import { BusEmitter } from './emitter'
import {
  beginConnectionEpoch,
  CLIENT_INSTANCE_ID,
  currentConnectionEpoch,
} from './clientCapabilities'
import type {
  Bus,
  ClientEventMap,
  ClientEventType,
  ConnectionStatus,
  ServerEventType,
  ServerHandler,
  Unsubscribe,
} from './types'

const RECONNECT_BASE_MS = 300
const RECONNECT_FACTOR = 1.7
const RECONNECT_MAX_MS = 8_000

/** §9.8: no frame of any kind for this long ⇒ the link is dead. */
const LIVENESS_TIMEOUT_MS = 12_000
/** How often the watchdog looks. Fine enough that the 12 s is really ~12 s. */
const LIVENESS_TICK_MS = 1_000

/** Events allowed through while we are waiting for a snapshot. Both are
 *  whole-value and orthogonal to scene state, and both matter to the operator
 *  precisely when things are going wrong. */
const PASSES_SNAPSHOT_GATE = new Set<string>(['error', 'mode.changed'])

export interface WsBusOptions {
  url: string
  role: 'stage' | 'control'
  /** Last `stateVersion` we know about, read fresh at each hello. */
  getStateVersion: () => number
}

export class WsBus implements Bus {
  readonly role: 'stage' | 'control'
  readonly clientInstanceId = CLIENT_INSTANCE_ID

  #url: string
  #getStateVersion: () => number
  #emitter = new BusEmitter()

  #socket: WebSocket | null = null
  #closedByUs = false

  /** last accepted inbound seq for THIS connection; null = none yet */
  #inSeq: number | null = null
  /** our own outbound counter; also per-connection */
  #outSeq = 0
  #stateVersion = 0
  #awaitingSnapshot = true

  #status: ConnectionStatus = {
    state: 'closed',
    attempts: 0,
    retryInMs: 0,
    lastHeartbeatAt: 0,
    latencyMs: null,
    lastFrameAt: 0,
  }
  #retryTimer: ReturnType<typeof setTimeout> | null = null

  /** §9.8 watchdog. Runs only while a socket is open. */
  #liveTimer: ReturnType<typeof setInterval> | null = null
  #lastFrameAt = 0

  constructor(options: WsBusOptions) {
    this.#url = options.url
    this.role = options.role
    this.#getStateVersion = options.getStateVersion
  }

  // ── lifecycle ──────────────────────────────────────────────────────────

  connect(): void {
    if (this.#socket && this.#socket.readyState <= WebSocket.OPEN) return
    this.#closedByUs = false
    this.#clearRetry()
    this.#setStatus({
      state: this.#status.attempts > 0 ? 'reconnecting' : 'connecting',
      retryInMs: 0,
    })

    let socket: WebSocket
    try {
      socket = new WebSocket(this.#url)
    } catch (err) {
      this.#scheduleReconnect(String(err))
      return
    }
    this.#socket = socket

    // Every handler below is guarded on `socket === this.#socket`.
    //
    // Without that guard a superseded socket keeps mutating state that now
    // belongs to its replacement. That is not theoretical — it was the cause of
    // a real freeze: StrictMode's mount/unmount/mount ran close() then
    // connect(), and the FIRST socket's late `onclose` then (a) nulled
    // `#socket`, orphaning the live second socket, and (b) saw `#closedByUs`
    // already reset to false by connect() and so scheduled a reconnect,
    // producing a third. Two live sockets fed one store with independent
    // per-connection seq spaces, the gap detector concluded frames were lost,
    // and the stage wedged on idle forever.
    const isCurrent = () => socket === this.#socket

    socket.onopen = () => {
      if (!isCurrent()) return
      // New connection ⇒ new seq space, and no trustworthy local state.
      this.#inSeq = null
      beginConnectionEpoch()
      this.#outSeq = 0
      this.#awaitingSnapshot = true
      this.#lastFrameAt = Date.now()
      // PROTOCOL: client.hello is the mandatory first frame. Publishing the
      // open status before this let BusProvider's capability reporter win the
      // callback race and Core correctly closed the socket as malformed.
      this.#hello()
      this.#setStatus({
        state: 'open',
        attempts: 0,
        retryInMs: 0,
        lastError: undefined,
        lastHeartbeatAt: 0,
        latencyMs: null,
        lastFrameAt: this.#lastFrameAt,
      })
      this.#armLiveness()
      this.#emitter.emitReset('connected')
    }

    socket.onmessage = (ev) => {
      if (!isCurrent()) return
      this.#receive(ev.data)
    }

    socket.onerror = () => {
      if (!isCurrent()) return
      this.#status = { ...this.#status, lastError: 'socket error' }
    }

    socket.onclose = (ev) => {
      if (!isCurrent()) return
      this.#socket = null
      this.#clearLiveness()
      if (this.#closedByUs) {
        this.#setStatus({ state: 'closed', attempts: 0, retryInMs: 0 })
        return
      }
      this.#scheduleReconnect(ev.reason || `closed (code ${ev.code})`)
    }
  }

  close(): void {
    this.#closedByUs = true
    this.#clearRetry()
    this.#clearLiveness()
    const socket = this.#socket
    this.#socket = null
    if (socket) {
      // Detach before closing. `#socket` is already null, so the isCurrent()
      // guard would drop these anyway, but silencing them outright means a
      // half-closed socket cannot emit anything during teardown.
      socket.onopen = null
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
      socket.close(1000, 'client shutdown')
    }
    this.#setStatus({ state: 'closed', attempts: 0, retryInMs: 0 })
  }

  connectionEpoch(): number {
    return currentConnectionEpoch()
  }

  // ── outbound ───────────────────────────────────────────────────────────

  send<K extends ClientEventType>(type: K, payload: ClientEventMap[K]): void {
    this.#dispatch({
      v: PROTOCOL_VERSION,
      type,
      seq: ++this.#outSeq,
      stateVersion: this.#stateVersion,
      ts: Date.now(),
      payload,
    })
  }

  requestSnapshot(reason: string): void {
    console.warn('[bus] resnapshot:', reason)
    this.#awaitingSnapshot = true
    this.#emitter.emitReset(reason)
    this.#hello()
  }

  #hello(): void {
    this.#stateVersion = this.#getStateVersion()
    this.send('client.hello', {
      role: this.role,
      stateVersion: this.#stateVersion,
    })
  }

  #dispatch(event: Event<unknown>): void {
    const socket = this.#socket
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(event))
      return
    }
    // Never replay classroom actions across a reconnect. They were created
    // against an old board/activity and can grade the wrong learner state.
    // Explicit idempotent workflows (for example lesson.start) already expose
    // UI retry instead of relying on a hidden transport queue.
  }

  // ── inbound ────────────────────────────────────────────────────────────

  #receive(data: unknown): void {
    // §9.8: ANY frame proves the link is alive — including a malformed one,
    // which is a server bug, not a dead link. So this is the first statement
    // in the method, before every rejection path below.
    this.#lastFrameAt = Date.now()

    if (typeof data !== 'string') {
      console.error('[bus] non-text frame rejected')
      return
    }

    let event: Event<unknown>
    try {
      event = JSON.parse(data) as Event<unknown>
    } catch {
      console.error('[bus] unparseable frame rejected:', data.slice(0, 200))
      return
    }

    if (!event || typeof event !== 'object' || typeof event.type !== 'string') {
      console.error('[bus] malformed envelope rejected', event)
      return
    }

    // Rule 3: reject an unknown protocol version loudly rather than guessing.
    if (event.v !== PROTOCOL_VERSION) {
      console.error(
        `[bus] protocol version ${String(event.v)} rejected (this client speaks ${PROTOCOL_VERSION})`,
      )
      this.#setStatus({ lastError: `unsupported protocol version ${String(event.v)}` })
      return
    }

    // §9.8: a heartbeat is out of band. It consumes no `seq` and never bumps
    // `stateVersion`, so it must be handled BEFORE the seq gate — whatever the
    // server puts in that field (0, or a repeat of the last value) would
    // otherwise read as a duplicate to drop or, worse, as a gap to resnapshot
    // over. It is also never forwarded to the emitter: no component should
    // have to know the link is being proved. `ConnectionStatus` carries it.
    if (event.type === 'heartbeat') {
      const ts = Number((event.payload as HeartbeatPayload | undefined)?.ts)
      const now = this.#lastFrameAt
      this.#ack(Number.isFinite(ts) ? ts : now)
      this.#setStatus({
        lastHeartbeatAt: now,
        latencyMs: Number.isFinite(ts) ? Math.max(0, now - ts) : null,
        lastFrameAt: now,
      })
      return
    }

    // Rule 2: seq is monotonic per connection.
    if (typeof event.seq === 'number') {
      if (this.#inSeq !== null) {
        if (event.seq <= this.#inSeq) {
          console.warn(`[bus] stale/duplicate seq ${event.seq} (have ${this.#inSeq}) — dropped`)
          return
        }
        if (event.seq !== this.#inSeq + 1) {
          const missed = event.seq - this.#inSeq - 1
          this.#inSeq = event.seq
          this.requestSnapshot(`seq gap: missed ${missed} event(s) before ${event.seq}`)
          return
        }
      }
      this.#inSeq = event.seq
    }

    if (typeof event.stateVersion === 'number' && event.stateVersion > this.#stateVersion) {
      this.#stateVersion = event.stateVersion
    }

    if (this.#awaitingSnapshot) {
      if (event.type === 'scene.snapshot') {
        this.#awaitingSnapshot = false
      } else if (!PASSES_SNAPSHOT_GATE.has(event.type)) {
        // Never patch across a gap: hold everything until the snapshot lands.
        return
      }
    }

    this.#emitter.emit(event)
  }

  // ── liveness (§9.8) ────────────────────────────────────────────────────

  /**
   * Echo the `ts` we were given, straight back.
   *
   * Never through `#dispatch`: an ack is only meaningful on the socket it
   * answers, so it must not be queued for a future connection. It does take a
   * normal outbound `seq` — §9.2 says the server ignores ours, and inventing a
   * special value would be a second rule for no benefit.
   */
  #ack(ts: number): void {
    const socket = this.#socket
    if (socket?.readyState !== WebSocket.OPEN) return
    socket.send(
      JSON.stringify({
        v: PROTOCOL_VERSION,
        type: 'heartbeat.ack',
        seq: ++this.#outSeq,
        stateVersion: this.#stateVersion,
        ts: Date.now(),
        payload: { ts } satisfies HeartbeatPayload,
      }),
    )
  }

  #armLiveness(): void {
    this.#clearLiveness()
    this.#liveTimer = setInterval(() => {
      const silent = Date.now() - this.#lastFrameAt
      if (silent < LIVENESS_TIMEOUT_MS) return
      this.#declareDead(silent)
    }, LIVENESS_TICK_MS)
  }

  #clearLiveness(): void {
    if (this.#liveTimer !== null) {
      clearInterval(this.#liveTimer)
      this.#liveTimer = null
    }
  }

  /**
   * The socket says OPEN and nothing has arrived for 12 s. Do NOT wait for
   * `onclose` — on a black-holed link that is the ~32 s (or the forever) this
   * whole mechanism exists to remove. Detach, close, and reconnect ourselves.
   */
  #declareDead(silentMs: number): void {
    const socket = this.#socket
    this.#clearLiveness()
    this.#socket = null
    if (socket) {
      socket.onopen = null
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
      try {
        socket.close(4000, 'link silent')
      } catch {
        /* already gone */
      }
    }
    // A dead link is not trustworthy state. The reconnect will resnapshot,
    // but the board must stop showing a frozen scene as if it were live.
    this.#awaitingSnapshot = true
    this.#emitter.emitReset(`link silent for ${Math.round(silentMs / 1000)}s`)
    this.#scheduleReconnect(`no frame for ${Math.round(silentMs / 1000)}s — link declared dead`)
  }

  // ── reconnect ──────────────────────────────────────────────────────────

  #scheduleReconnect(reason: string): void {
    const attempts = this.#status.attempts + 1
    const raw = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * RECONNECT_FACTOR ** (attempts - 1))
    const delay = Math.round(raw * (0.85 + Math.random() * 0.3))
    this.#setStatus({
      state: 'reconnecting',
      attempts,
      retryInMs: delay,
      lastError: reason,
      // Liveness telemetry belongs to a connection; a stale "12 ms" beside a
      // reconnecting badge would read as "the link is fine".
      lastHeartbeatAt: 0,
      latencyMs: null,
    })
    this.#clearRetry()
    this.#retryTimer = setTimeout(() => {
      this.#retryTimer = null
      this.connect()
    }, delay)
  }

  #clearRetry(): void {
    if (this.#retryTimer !== null) {
      clearTimeout(this.#retryTimer)
      this.#retryTimer = null
    }
  }

  // ── subscriptions ──────────────────────────────────────────────────────

  on<K extends ServerEventType>(type: K, handler: ServerHandler<K>): Unsubscribe {
    return this.#emitter.on(type, handler)
  }

  onAny(handler: (event: Event<unknown>) => void): Unsubscribe {
    return this.#emitter.onAny(handler)
  }

  onStatus(handler: (status: ConnectionStatus) => void): Unsubscribe {
    return this.#emitter.onStatus(handler)
  }

  onReset(handler: (reason: string) => void): Unsubscribe {
    return this.#emitter.onReset(handler)
  }

  status(): ConnectionStatus {
    return this.#status
  }

  #setStatus(patch: Partial<ConnectionStatus>): void {
    this.#status = { ...this.#status, ...patch }
    this.#emitter.emitStatus(this.#status)
  }
}
