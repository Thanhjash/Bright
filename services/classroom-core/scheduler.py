"""Background work -- the three jobs from docs/archive/phase-1-plan.md §6.

============================  ==========================  =======================
job                           when                        does
============================  ==========================  =======================
``summarize_session``         30 s after a session ends   agent reads the session's
                                                          observations -> summary
``prepare_next``              nightly, or on demand       weak points -> next run
``health_probe``              every 60 s                  sets FULL/DEGRADED/OFFLINE
============================  ==========================  =======================

``services/agent`` is built by another agent, so the agent-calling parts sit
behind :class:`AgentSeam` -- a bundle of callables that default to no-ops.  No
LLM call is ever made from this service; the seam is injected at startup.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from modes import AgentProbe, null_probe

log = logging.getLogger("classroom_core.scheduler")

SummarizeFn = Callable[[str, list[dict[str, Any]]], Awaitable[dict[str, Any] | None] | dict[str, Any] | None]
PrepareFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None] | dict[str, Any] | None]


async def _noop_summarize(session_id: str, observations: list[dict[str, Any]]) -> None:
    """Default: record nothing. The real one reads observations and writes prose."""
    return None


async def _noop_prepare(context: dict[str, Any]) -> None:
    """Default: no lesson compilation. The real one emits a lesson_run.json."""
    return None


@dataclass
class AgentSeam:
    """Everything classroom-core would like an agent for, and can live without."""

    summarize_session: SummarizeFn = field(default=_noop_summarize)
    prepare_next: PrepareFn = field(default=_noop_prepare)
    probe: AgentProbe = field(default=null_probe)


async def _call(fn: Callable[..., Any], *args: Any) -> Any:
    result = fn(*args)
    if inspect.isawaitable(result):
        return await result
    return result


class BackgroundJobs:
    def __init__(
        self,
        db: Any,
        mode_controller: Any,
        seam: AgentSeam | None = None,
        *,
        probe_interval_s: int = 60,
        summary_delay_s: int = 30,
        prepare_next_hour: int = 3,
        recheck_after_s: float = 5.0,
    ) -> None:
        self.db = db
        self.modes = mode_controller
        self.seam = seam or AgentSeam()
        self.probe_interval_s = probe_interval_s
        self.summary_delay_s = summary_delay_s
        self.prepare_next_hour = prepare_next_hour
        self.recheck_after_s = recheck_after_s
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.started = False
        # A live turn that failed already demoted the mode without waiting for
        # the interval; the way back should not have to wait for it either.
        if self.modes is not None and hasattr(self.modes, "on_fast_degrade"):
            self.modes.on_fast_degrade = self.recheck_soon

    # ------------------------------------------------------------- wiring
    def set_seam(self, seam: AgentSeam) -> None:
        self.seam = seam
        if self.modes is not None:
            self.modes.set_probe(seam.probe)

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self.started:
            return
        self.scheduler.add_job(
            self.health_probe,
            IntervalTrigger(seconds=self.probe_interval_s),
            id="health_probe",
            replace_existing=True,
            max_instances=1,
            next_run_time=datetime.now(timezone.utc),
        )
        self.scheduler.add_job(
            self.prepare_next,
            CronTrigger(hour=self.prepare_next_hour, minute=0),
            id="prepare_next",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        self.started = True

    def shutdown(self) -> None:
        if self.started:
            self.scheduler.shutdown(wait=False)
            self.started = False

    def jobs(self) -> list[dict[str, Any]]:
        return [
            {
                "id": job.id,
                "nextRunTime": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in self.scheduler.get_jobs()
        ]

    # ---------------------------------------------------------------- jobs
    async def health_probe(self) -> str | None:
        if self.modes is None:
            return None
        try:
            return await self.modes.health_probe()
        except Exception:  # noqa: BLE001 - a broken probe must not kill the scheduler
            log.exception("health_probe failed")
            return None

    def recheck_soon(self, delay_s: float | None = None) -> None:
        """Bring the next health probe forward, without disturbing the interval.

        ``job.modify(next_run_time=...)`` moves only the next firing; the
        ``IntervalTrigger`` keeps computing from there, so the probe is not
        removed, replaced or accelerated permanently -- it just stops being up
        to a whole minute stale at the one moment its answer matters.
        """
        if not self.started:
            return
        job = self.scheduler.get_job("health_probe")
        if job is None:
            return
        when = datetime.now(timezone.utc) + timedelta(
            seconds=self.recheck_after_s if delay_s is None else delay_s
        )
        if job.next_run_time is not None and job.next_run_time <= when:
            return  # already coming sooner than we would ask for
        try:
            job.modify(next_run_time=when)
        except Exception:  # noqa: BLE001 - the interval probe is still armed
            log.exception("could not bring the health probe forward")

    def schedule_session_summary(self, session_id: str, delay_s: int | None = None) -> None:
        """Queue ``summarize_session`` for N seconds after the session ended."""
        when = datetime.now(timezone.utc) + timedelta(
            seconds=self.summary_delay_s if delay_s is None else delay_s
        )
        if not self.started:
            self.scheduler.start()
            self.started = True
        self.scheduler.add_job(
            self.summarize_session,
            DateTrigger(run_date=when),
            args=[session_id],
            id=f"summarize_session:{session_id}",
            replace_existing=True,
        )

    async def summarize_session(self, session_id: str) -> dict[str, Any] | None:
        observations = self.db.list_observations(session_id=session_id) if self.db else []
        try:
            result = await _call(self.seam.summarize_session, session_id, observations)
        except Exception:  # noqa: BLE001
            log.exception("summarize_session seam failed for %s", session_id)
            return None
        if not result or self.db is None:
            return None
        summary = self.db.write_session_summary(
            session_id,
            str(result.get("summary", "")),
            result.get("weakPoints") or result.get("weak_points") or [],
            result.get("nextFocus") or result.get("next_focus") or [],
        )
        for skill, estimate in (result.get("skills") or {}).items():
            student_id = result.get("studentId") or result.get("student_id")
            if student_id:
                self.db.update_skill(student_id, skill, float(estimate))
        return summary

    async def prepare_next(self, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        payload = dict(context or {})
        try:
            return await _call(self.seam.prepare_next, payload)
        except Exception:  # noqa: BLE001
            log.exception("prepare_next seam failed")
            return None


__all__ = ["BackgroundJobs", "AgentSeam", "SummarizeFn", "PrepareFn"]
