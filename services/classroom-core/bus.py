"""In-process publish/subscribe event bus.

Every frame that leaves classroom-core goes through here, so that the two
load-bearing fields of PROTOCOL.md §1 have exactly one owner:

* ``seq``          -- monotonic **per connection**, allocated at enqueue time.
* ``stateVersion`` -- global, read from the state store at enqueue time.

A subscriber whose queue overflows is marked ``dropped``: rather than emit a
gap we close the connection and let the client reconnect and take a fresh
snapshot ("never patch across a gap").
"""

from __future__ import annotations

import asyncio
import itertools
import time
from typing import Any, Callable, Iterable

from pydantic import BaseModel

import config  # noqa: F401  -- installs the bright_contracts import path
from bright_contracts import PROTOCOL_VERSION, Event

_conn_ids = itertools.count(1)


def now_ms() -> int:
    return int(time.time() * 1000)


def to_wire(value: Any) -> Any:
    """Recursively convert pydantic models to camelCase JSON-safe primitives.

    Necessary because ``Event.payload`` is typed ``Any``; pydantic does not
    apply ``by_alias`` to models nested under an untyped field, so payloads are
    normalised *before* the envelope is built.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {k: to_wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_wire(v) for v in value]
    return value


class Subscriber:
    """One connected client.

    Liveness state (PROTOCOL §9.8) lives here rather than in the socket handler
    so that ``/dev/state`` can report the round trip a facilitator cares about:
    a link at 400 ms is working, a link at 4 s is about to fail.
    """

    __slots__ = (
        "id", "role", "queue", "_seq", "dropped", "drop_reason", "closed",
        "heartbeats", "acks", "last_ack", "rtt_ms",
    )

    def __init__(self, role: str = "stage", maxsize: int = 512) -> None:
        self.id = next(_conn_ids)
        self.role = role
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._seq = 0
        self.dropped = False
        self.drop_reason = "event backlog; reconnect for a snapshot"
        self.closed = asyncio.Event()
        #: How many heartbeats we have sent this connection.
        self.heartbeats = 0
        #: How many ``heartbeat.ack`` frames came back.
        self.acks = 0
        #: ``time.monotonic()`` of the last ack. ``None`` = never acked, which
        #: is how a pre-§9.8 client is told apart from a link that has died.
        self.last_ack: float | None = None
        #: Last measured round trip, milliseconds.
        self.rtt_ms: float | None = None

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def speaks_heartbeat(self) -> bool:
        """True once this client has proved it implements §9.8."""
        return self.last_ack is not None

    def note_ack(self, sent_ts_ms: int | None = None) -> None:
        now = time.monotonic()
        self.acks += 1
        self.last_ack = now
        if sent_ts_ms:
            self.rtt_ms = max(0.0, now_ms() - float(sent_ts_ms))

    def silent_for(self) -> float | None:
        """Seconds since the last ack, or ``None`` if it has never acked."""
        if self.last_ack is None:
            return None
        return time.monotonic() - self.last_ack

    def drop(self, reason: str) -> None:
        """Mark for close and reclaim the queue.

        The frames still queued are unreachable by definition -- the client
        they were addressed to is gone -- and holding them keeps up to
        ``queue_maxsize`` scenes alive per dead link.
        """
        self.dropped = True
        self.drop_reason = reason
        self.closed.set()
        while True:
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Subscriber #{self.id} role={self.role} seq={self._seq}>"


class EventBus:
    def __init__(
        self,
        state_version_provider: Callable[[], int] | None = None,
        *,
        queue_maxsize: int = 512,
    ) -> None:
        self._subs: dict[int, Subscriber] = {}
        self._queue_maxsize = queue_maxsize
        self._state_version_provider = state_version_provider or (lambda: 0)
        self.history: list[dict[str, Any]] = []   # last N frames, for /dev/state + tests
        self._history_limit = 100

    # ------------------------------------------------------------- wiring
    def set_state_version_provider(self, provider: Callable[[], int]) -> None:
        self._state_version_provider = provider

    @property
    def state_version(self) -> int:
        return self._state_version_provider()

    @property
    def subscribers(self) -> Iterable[Subscriber]:
        return tuple(self._subs.values())

    @property
    def connection_count(self) -> int:
        return len(self._subs)

    # --------------------------------------------------------- membership
    def subscribe(self, role: str = "stage") -> Subscriber:
        sub = Subscriber(role=role, maxsize=self._queue_maxsize)
        self._subs[sub.id] = sub
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subs.pop(sub.id, None)
        sub.closed.set()

    # ------------------------------------------------------------ publish
    def _frame(self, sub: Subscriber, type_: str, payload: Any) -> dict[str, Any]:
        event = Event(
            v=PROTOCOL_VERSION,
            type=type_,           # type: ignore[arg-type]
            seq=sub.next_seq(),
            state_version=self.state_version,
            ts=now_ms(),
            payload=to_wire(payload),
        )
        return event.model_dump(mode="json", by_alias=True)

    def _enqueue(self, sub: Subscriber, type_: str, payload: Any) -> dict[str, Any] | None:
        if sub.dropped:
            # Its queue has already been reclaimed and its socket is closing.
            # Refilling it would leak the memory the drop just freed.
            return None
        frame = self._frame(sub, type_, payload)
        try:
            sub.queue.put_nowait(frame)
        except asyncio.QueueFull:
            # A gap is unrecoverable for the client; drop the connection so it
            # reconnects and takes a full snapshot.
            sub.drop("event backlog; reconnect for a snapshot")
            return None
        return frame

    def send(self, sub: Subscriber, type_: str, payload: Any = None) -> dict[str, Any] | None:
        """Send one frame to one subscriber, using that connection's seq."""
        frame = self._enqueue(sub, type_, payload)
        self._remember(frame)
        return frame

    # ------------------------------------------------------- out-of-band
    def send_oob(self, sub: Subscriber, type_: str, payload: Any = None) -> dict[str, Any] | None:
        """Send a frame that is **not part of the event stream** (PROTOCOL §9.8).

        No ``seq`` is allocated and the key is omitted entirely, because every
        value is worse: a repeated seq reads as a duplicate, a zero or a skip
        reads as a gap, and a fresh one would make a reconnecting client's
        arithmetic wrong. A receiver keeps counting the stream it can see.

        ``stateVersion`` *is* stamped -- truthfully, at its current value. The
        rule is that a heartbeat must not **bump** the version, not that it may
        not carry it; omitting it would look like a regression to a client that
        tracks the highest version seen.

        Not remembered in ``history`` either: 12 heartbeats a minute would
        evict everything ``/dev/state`` exists to show.
        """
        if sub.dropped:
            return None
        frame = {
            "v": PROTOCOL_VERSION,
            "type": type_,
            "stateVersion": self.state_version,
            "ts": now_ms(),
            "payload": to_wire(payload),
        }
        try:
            sub.queue.put_nowait(frame)
        except asyncio.QueueFull:
            sub.drop("event backlog; reconnect for a snapshot")
            return None
        return frame

    def publish(self, type_: str, payload: Any = None) -> int:
        """Broadcast to every connected subscriber. Returns the fan-out count."""
        wire = to_wire(payload)
        sent = 0
        remembered = False
        for sub in tuple(self._subs.values()):
            frame = self._enqueue(sub, type_, wire)
            if frame is not None:
                sent += 1
                if not remembered:
                    self._remember(frame)
                    remembered = True
        if not remembered:
            # Nobody connected: still record it so /dev/state and tests can see
            # what the core decided to emit.
            self._remember(
                {
                    "v": PROTOCOL_VERSION,
                    "type": type_,
                    "seq": 0,
                    "stateVersion": self.state_version,
                    "ts": now_ms(),
                    "payload": wire,
                }
            )
        return sent

    def _remember(self, frame: dict[str, Any] | None) -> None:
        if frame is None:
            return
        self.history.append(frame)
        if len(self.history) > self._history_limit:
            del self.history[: len(self.history) - self._history_limit]


__all__ = ["EventBus", "Subscriber", "to_wire", "now_ms"]
