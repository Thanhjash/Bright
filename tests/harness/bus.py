"""A protocol-correct WebSocket client for the classroom bus.

Deliberately not a copy of the UI's client: if both sides came from the same
source, a shared misreading of `PROTOCOL.md` would agree with itself and the
test would pass. This one is written from the protocol document, and it
enforces the two invariants the document calls load-bearing:

* `seq` is strictly monotonic per connection, starting at 1, **with no gaps**.
  A gap means the client missed something; §9.8 says the server must close the
  socket (1011) rather than let one happen. `gaps` records any it sees.
* `stateVersion` never goes backwards.

Both are checked on every frame, so any test that runs a lesson is also, for
free, a test that the bus stayed honest for the whole lesson.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable

import websockets


class SeqGap(Exception):
    pass


class BusClient:
    def __init__(self, url: str, role: str = "stage") -> None:
        self.url = url
        self.role = role
        self.events: list[dict[str, Any]] = []
        self.gaps: list[tuple[int, int]] = []
        self.version_regressions: list[tuple[int, int]] = []
        self.last_seq = 0
        self.state_version = 0
        self.closed_code: int | None = None
        self.heartbeats = 0
        self._ws: Any = None
        self._task: asyncio.Task[None] | None = None
        self._out_seq = 0

    # ------------------------------------------------------------- lifecycle

    async def connect(self, hello: bool = True, state_version: int | None = None) -> None:
        self._ws = await websockets.connect(self.url, open_timeout=15, max_queue=None)
        self._task = asyncio.create_task(self._pump())
        if hello:
            await self.hello(state_version)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def __aenter__(self) -> "BusClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ----------------------------------------------------------------- send

    async def send(self, type_: str, payload: dict[str, Any]) -> None:
        self._out_seq += 1
        frame = {
            "v": 2,
            "type": type_,
            "seq": self._out_seq,
            "stateVersion": self.state_version,
            "ts": int(time.time() * 1000),
            "payload": payload,
        }
        await self._ws.send(json.dumps(frame))

    async def _ack(self, heartbeat: dict[str, Any]) -> None:
        """Echo the `ts` we were sent (PROTOCOL §9.8). Never fatal."""
        try:
            await self.send("heartbeat.ack", {"ts": (heartbeat.get("payload") or {}).get("ts")})
        except Exception:  # noqa: BLE001 - the socket is closing; the test reads closed_code
            pass

    async def hello(self, state_version: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role}
        if state_version is not None:
            payload["stateVersion"] = state_version
        await self.send("client.hello", payload)
        return await self.wait_for("scene.snapshot", timeout=15)

    async def choose(self, option_id: str, student_id: str | None = None) -> None:
        payload: dict[str, Any] = {"optionId": option_id}
        if student_id:
            payload["studentId"] = student_id
        await self.send("interaction.choice", payload)

    # ----------------------------------------------------------------- recv

    async def _pump(self) -> None:
        try:
            async for raw in self._ws:
                event = json.loads(raw)
                if event.get("type") == "heartbeat":
                    # PROTOCOL §9.8: out-of-band. It carries no `seq` at all,
                    # so it must be kept out of the gap arithmetic — counting
                    # it is exactly the phantom gap the frame is shaped to
                    # avoid. Acking it also means every test that holds a
                    # socket open exercises the server's liveness path.
                    self.events.append(event)
                    self.heartbeats += 1
                    await self._ack(event)
                    continue
                seq = int(event.get("seq") or 0)
                if self.last_seq and seq != self.last_seq + 1:
                    self.gaps.append((self.last_seq, seq))
                self.last_seq = seq
                sv = int(event.get("stateVersion") or 0)
                if sv < self.state_version:
                    self.version_regressions.append((self.state_version, sv))
                self.state_version = max(self.state_version, sv)
                self.events.append(event)
        except websockets.exceptions.ConnectionClosed as exc:
            self.closed_code = exc.code
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the test reads `closed_code`
            self.closed_code = -1

    # ---------------------------------------------------------------- query

    def of_type(self, type_: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("type") == type_]

    def scenes(self, since: int = 0) -> list[dict[str, Any]]:
        out = []
        for e in self.events[since:]:
            if e.get("type") == "scene.update":
                out.append(e["payload"])
            elif e.get("type") == "scene.snapshot":
                out.append(e["payload"]["scene"])
        return out

    def cursor(self) -> int:
        """Index of the next event to arrive.

        Pass it as `since=` so a wait cannot be satisfied by something the
        client saw earlier in the test. Without it, "wait for a vocabulary
        scene" matches a vocabulary scene from three activities ago and the
        test races ahead of the lesson — which is exactly how an
        order-dependent, intermittent failure gets built.
        """
        return len(self.events)

    def spoken(self) -> list[str]:
        return [str(e["payload"].get("text") or "") for e in self.of_type("speech.say")]

    async def wait_for(
        self,
        type_: str,
        timeout: float = 30.0,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
        since: int | None = None,
    ) -> dict[str, Any]:
        start = since if since is not None else 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.events[start:]:
                if event.get("type") == type_ and (predicate is None or predicate(event)):
                    return event
            start = len(self.events)
            await asyncio.sleep(0.02)
        raise TimeoutError(
            f"no {type_} within {timeout}s "
            f"(saw {[e.get('type') for e in self.events[-12:]]})"
        )

    async def wait_for_scene(
        self, kind: str, timeout: float = 60.0, since: int | None = None
    ) -> dict[str, Any]:
        start = since if since is not None else 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for scene in reversed(self.scenes(start)):
                if scene.get("kind") == kind:
                    return scene
            await asyncio.sleep(0.05)
        raise TimeoutError(
            f"scene kind={kind!r} never appeared; saw {[s.get('kind') for s in self.scenes(start)]}"
        )

    def assert_clean(self) -> None:
        assert not self.gaps, f"seq gaps on the bus: {self.gaps}"
        assert not self.version_regressions, f"stateVersion went backwards: {self.version_regressions}"
