"""FULL / DEGRADED / OFFLINE (PROTOCOL.md §7, docs/3-design/architecture.md §2).

The mode is a *measurement*, never a setting the teacher is asked about.  A
``health_probe`` calls the injected agent seam, times it, and moves the mode:

    latency < full_max_latency_s        -> FULL      (agent drives)
    latency < degraded_max_latency_s    -> DEGRADED  (core plays lesson_run)
    unreachable / timeout / no agent    -> OFFLINE   (core plays it alone)

Degrading is immediate (a class is waiting).  Recovering requires
``recover_after`` consecutive good probes, so a single lucky reply cannot flap
the badge back and forth.

**The probe is not the only signal.**  It fires every 60 s, and a live turn
that fails is a health measurement that has *already happened* -- more recent,
and about the exact call the class is waiting on.  Left to the probe alone, a
cloud outage costs a six-second hole per answered question for up to a minute
before the badge catches up.  So ``note_agent_turn`` feeds real turns into the
same state machine: ``degrade_after`` consecutive failures demote immediately,
one success clears the run, and recovery goes through the identical
``recover_after`` streak the probe uses.  A turn-driven demotion also pulls the
next probe forward (``on_fast_degrade``), so coming back is as quick as going
down; the probe still owns recovery, because no turn is offered below FULL.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Awaitable, Callable

import config  # noqa: F401  -- installs the bright_contracts import path
from bright_contracts import Mode

log = logging.getLogger("classroom_core.modes")

# The seam: returns measured latency in seconds, or None when there is no
# agent to talk to.  services/agent injects the real one at startup.
AgentProbe = Callable[[], Awaitable[float | None] | float | None]


async def null_probe() -> None:
    """Default seam: no agent configured -> OFFLINE. No LLM call ever lives here."""
    return None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class ModeController:
    def __init__(
        self,
        store: Any,
        bus: Any,
        probe: AgentProbe | None = None,
        *,
        full_max_latency_s: float = 3.0,
        degraded_max_latency_s: float = 10.0,
        recover_after: int = 2,
        degrade_after: int = 2,
        forced_mode: Mode | None = None,
        on_fast_degrade: Callable[[], Any] | None = None,
    ) -> None:
        self.store = store
        self.bus = bus
        self.probe: AgentProbe = probe or null_probe
        self.full_max_latency_s = full_max_latency_s
        self.degraded_max_latency_s = degraded_max_latency_s
        self.recover_after = max(1, recover_after)
        #: Consecutive failed live turns before the mode drops without waiting
        #: for a probe. One is a hiccup; two in a row is an outage, and every
        #: one of them costs the class the full turn timeout.
        self.degrade_after = max(1, degrade_after)
        self.forced_mode = forced_mode
        #: Called when a *turn* demoted the mode, so whoever owns the schedule
        #: can bring the next probe forward. Optional: nothing here schedules.
        self.on_fast_degrade = on_fast_degrade
        self.last_latency_s: float | None = None
        self.last_turn_latency_s: float | None = None
        self.last_reason = "startup"
        self.turn_failures = 0          # current consecutive run
        self.turn_failures_total = 0
        self.fast_degrades = 0
        self._good_streak = 0
        self._lock = asyncio.Lock()
        if forced_mode:
            self.apply(forced_mode, "pinned by CORE_MODE")

    _RANK = {"FULL": 2, "DEGRADED": 1, "OFFLINE": 0}

    def set_probe(self, probe: AgentProbe) -> None:
        """Wire in the real agent seam (services/agent) at startup."""
        self.probe = probe

    # ------------------------------------------------------------ applying
    def apply(self, mode: Mode, reason: str) -> bool:
        """Set the mode and emit ``mode.changed`` if it actually moved."""
        self.last_reason = reason
        if mode == "FULL":
            # Back at FULL the slate is clean: a failure run counted before the
            # outage was fixed must not put the very next turn one strike from
            # demoting again.
            self.turn_failures = 0
        if self.store.set_mode(mode):
            self.bus.publish("mode.changed", {"mode": mode, "reason": reason})
            # The badge lives in the scene overlay, so the stage needs the scene too.
            self.bus.publish("scene.update", self.store.scene)
            return True
        return False

    def _settle(self, target: Mode, reason: str) -> bool:
        """Move toward ``target``: down at once, up only on a streak.

        Shared by both health signals on purpose. A probe and a live turn are
        the same measurement taken at different moments, so they must not have
        two different opinions about how quickly the badge is allowed to move.
        """
        if self._RANK[target] > self._RANK[self.store.mode]:
            self._good_streak += 1
            if self._good_streak < self.recover_after:
                return False        # not yet: one lucky reply is not a recovery
        else:
            self._good_streak = 0
        return self.apply(target, reason)

    # ------------------------------------------------------- the turn signal
    def note_agent_turn(
        self,
        ok: bool,
        *,
        kind: str = "ok",
        latency_s: float | None = None,
        detail: str = "",
    ) -> Mode:
        """Report the outcome of a live agent turn. The fast health signal.

        ``kind`` says what a failure was, because the two are different modes:
        ``"timeout"`` is an agent that is alive and too slow -> DEGRADED;
        anything else (transport, refused connection, a raised error) is an
        agent that is not there -> OFFLINE.

        A turn that *completed* is a success here even if the agent chose
        nothing or chose something illegal: that is a pedagogy problem, not a
        health problem, and demoting for it would take the agent away from the
        class for being wrong rather than for being absent.
        """
        if self.forced_mode:
            return self.forced_mode
        if ok:
            self.turn_failures = 0
            self.last_turn_latency_s = latency_s
            return self.store.mode

        self.turn_failures += 1
        self.turn_failures_total += 1
        self.last_turn_latency_s = None
        if self.turn_failures < self.degrade_after:
            # One hole is a hiccup. Two in a row is an outage.
            return self.store.mode

        target: Mode = "DEGRADED" if kind == "timeout" else "OFFLINE"
        reason = f"{self.turn_failures} live agent turns failed in a row"
        if detail:
            reason = f"{reason} ({detail})"
        if self._settle(target, reason):
            self.fast_degrades += 1
            if self.on_fast_degrade is not None:
                try:
                    self.on_fast_degrade()
                except Exception:  # noqa: BLE001 - re-probing sooner is a nicety
                    log.exception("on_fast_degrade hook failed")
        return self.store.mode

    def stats(self) -> dict[str, Any]:
        return {
            "mode": self.store.mode,
            "reason": self.last_reason,
            "lastProbeLatencyMs": (
                int(self.last_latency_s * 1000) if self.last_latency_s is not None else None
            ),
            "lastTurnLatencyMs": (
                int(self.last_turn_latency_s * 1000)
                if self.last_turn_latency_s is not None
                else None
            ),
            "turnFailures": self.turn_failures,
            "turnFailuresTotal": self.turn_failures_total,
            "fastDegrades": self.fast_degrades,
            "degradeAfter": self.degrade_after,
            "recoverAfter": self.recover_after,
        }

    # ------------------------------------------------------------ probing
    async def health_probe(self) -> Mode:
        """One measurement. Safe to call from apscheduler."""
        if self.forced_mode:
            return self.forced_mode
        async with self._lock:
            started = time.perf_counter()
            latency: float | None
            reason: str
            try:
                result = await asyncio.wait_for(
                    _maybe_await(self.probe()), timeout=self.degraded_max_latency_s
                )
            except asyncio.TimeoutError:
                latency, reason = None, (
                    f"agent probe timed out after {self.degraded_max_latency_s:.0f}s"
                )
            except Exception as exc:  # noqa: BLE001 - any agent failure is OFFLINE
                latency, reason = None, f"agent probe failed: {type(exc).__name__}: {exc}"
            else:
                if result is None:
                    latency, reason = None, "no agent configured"
                else:
                    latency = float(result) if result else (time.perf_counter() - started)
                    reason = f"agent latency {latency * 1000:.0f}ms"

            self.last_latency_s = latency
            if latency is None:
                target: Mode = "OFFLINE"
            elif latency < self.full_max_latency_s:
                target = "FULL"
            elif latency < self.degraded_max_latency_s:
                target = "DEGRADED"
            else:
                target = "OFFLINE"

            self._settle(target, reason)
            return self.store.mode


__all__ = ["ModeController", "AgentProbe", "null_probe"]
