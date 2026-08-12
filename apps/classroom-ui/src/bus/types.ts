/**
 * The bus contract the rest of the app codes against.
 *
 * Two implementations satisfy it — `WsBus` (real classroom-core) and
 * `MockBus` (local fixture driver). Nothing downstream of this interface
 * knows which one it is talking to. That is what makes `VITE_MOCK=1` a
 * complete standalone demo rather than a special code path.
 */
import type {
  ActPayload,
  ClientHelloPayload,
  ControlCommandPayload,
  ErrorPayload,
  Event,
  InteractionChoicePayload,
  InteractionDragPayload,
  InteractionPointPayload,
  LessonPosition,
  LessonStartPayload,
  LessonStartedPayload,
  ModeChangedPayload,
  Scene,
  SceneSnapshotPayload,
  SpeechCancelPayload,
  SpeechBargeInAckPayload,
  SpeechBargeInPayload,
  SpeechPlaybackFinishedPayload,
  SpeechPlaybackStartedPayload,
  SpeechSayPayload,
  SpeechTextDeltaPayload,
  SpeechTurnEndedPayload,
  SpeechTurnStartedPayload,
  StudentSpeechFinalPayload,
  StudentResponseAcceptedPayload,
} from '@contracts'

/** server → client. Keys are exactly the `↓` rows of the event catalog. */
export interface ServerEventMap {
  'scene.update': Scene
  'scene.snapshot': SceneSnapshotPayload
  'speech.say': SpeechSayPayload
  'speech.turn.started': SpeechTurnStartedPayload
  'speech.text.delta': SpeechTextDeltaPayload
  'speech.turn.ended': SpeechTurnEndedPayload
  'student.response.accepted': StudentResponseAcceptedPayload
  'speech.cancel': SpeechCancelPayload
  'speech.barge_in.ack': SpeechBargeInAckPayload
  'avatar.act': ActPayload
  'lesson.position': LessonPosition
  'lesson.started': LessonStartedPayload
  'mode.changed': ModeChangedPayload
  error: ErrorPayload
}

/** client → server. Keys are exactly the `↑` rows of the event catalog. */
export interface ClientEventMap {
  'client.hello': ClientHelloPayload
  'interaction.choice': InteractionChoicePayload
  'interaction.point': InteractionPointPayload
  'interaction.drag': InteractionDragPayload
  'control.command': ControlCommandPayload
  'lesson.start': LessonStartPayload
  'student.speech.final': StudentSpeechFinalPayload
  'speech.playback.started': SpeechPlaybackStartedPayload
  'speech.playback.finished': SpeechPlaybackFinishedPayload
  'speech.barge_in': SpeechBargeInPayload
}

export type ServerEventType = keyof ServerEventMap
export type ClientEventType = keyof ClientEventMap

export type ConnectionState =
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'
  /** mock mode: no socket exists and none is wanted */
  | 'mock'

export interface ConnectionStatus {
  state: ConnectionState
  /** consecutive failed connects; 0 while healthy */
  attempts: number
  /** ms until the next reconnect attempt, when `reconnecting` */
  retryInMs: number
  /** last transport-level problem, for the facilitator console */
  lastError?: string

  // ── §9.8 liveness. UI-local telemetry, never on the wire. ──
  /** epoch ms of the last `heartbeat` received; 0 = none this connection */
  lastHeartbeatAt: number
  /**
   * `Date.now() - heartbeat.ts`, in ms.
   *
   * Server→client transit. On the shipped appliance both processes share one
   * machine and therefore one clock, so this is an honest link latency; across
   * two machines with unsynced clocks it carries a constant offset, which is
   * why the console labels it "link" and shows the beat gap beside it.
   * A link at 400 ms is working; a link at 4 s is about to fail (§9.8).
   */
  latencyMs: number | null
  /** epoch ms of the last frame of ANY kind. The watchdog's input. */
  lastFrameAt: number
}

export type Unsubscribe = () => void

export type ServerHandler<K extends ServerEventType> = (
  payload: ServerEventMap[K],
  event: Event<ServerEventMap[K]>,
) => void

export interface Bus {
  readonly role: 'stage' | 'control'
  connect(): void
  close(): void
  /** Wraps `payload` in a full `Event<T>` envelope and sends it. */
  send<K extends ClientEventType>(type: K, payload: ClientEventMap[K]): void
  on<K extends ServerEventType>(type: K, handler: ServerHandler<K>): Unsubscribe
  /** Every inbound event, post-validation. Used for the transcript/log. */
  onAny(handler: (event: Event<unknown>) => void): Unsubscribe
  onStatus(handler: (status: ConnectionStatus) => void): Unsubscribe
  status(): ConnectionStatus
  /**
   * Fires when local state must be thrown away wholesale: a `seq` gap, a
   * reconnect, or a protocol-version rejection. Subscribers clear their state
   * and wait for the `scene.snapshot` that follows.
   */
  onReset(handler: (reason: string) => void): Unsubscribe
  /**
   * Ask for a full snapshot and discard everything local.
   * PROTOCOL.md has no dedicated "resnapshot" event, so this re-sends
   * `client.hello` — `scene.snapshot` is defined as its reply.
   */
  requestSnapshot(reason: string): void
}
