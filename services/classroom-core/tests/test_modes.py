from __future__ import annotations

import asyncio

from modes import ModeController
from scheduler import AgentSeam, BackgroundJobs


def emitted(bus) -> list[dict]:
    return [f for f in bus.history if f["type"] == "mode.changed"]


async def test_default_seam_means_offline(store, bus):
    """No agent injected -> OFFLINE, and no LLM call is ever attempted."""
    modes = ModeController(store, bus)
    assert await modes.health_probe() == "OFFLINE"
    assert store.mode == "OFFLINE"
    assert modes.last_reason == "no agent configured"


async def test_fast_agent_promotes_to_full(store, bus):
    modes = ModeController(store, bus, probe=lambda: 0.4, recover_after=2)
    assert await modes.health_probe() == "OFFLINE"   # first good probe: streak 1
    assert await modes.health_probe() == "FULL"      # second: promoted
    assert store.mode == "FULL"
    changes = emitted(bus)
    assert changes[-1]["payload"]["mode"] == "FULL"
    assert "latency" in changes[-1]["payload"]["reason"]


async def test_slow_agent_degrades_immediately(store, bus):
    modes = ModeController(store, bus, probe=lambda: 0.1, recover_after=1)
    await modes.health_probe()
    assert store.mode == "FULL"

    modes.set_probe(lambda: 5.0)                     # slow, but alive
    assert await modes.health_probe() == "DEGRADED"
    assert store.mode == "DEGRADED"
    assert emitted(bus)[-1]["payload"]["mode"] == "DEGRADED"
    # the stage learns about the badge through the scene too
    assert store.scene.overlay.mode_badge == "DEGRADED"


async def test_failing_agent_goes_offline(store, bus):
    async def boom() -> float:
        raise ConnectionRefusedError("agent is down")

    modes = ModeController(store, bus, probe=lambda: 0.1, recover_after=1)
    await modes.health_probe()
    assert store.mode == "FULL"

    modes.set_probe(boom)
    assert await modes.health_probe() == "OFFLINE"
    assert "ConnectionRefusedError" in modes.last_reason


async def test_probe_timeout_goes_offline(store, bus):
    async def hang() -> float:
        await asyncio.sleep(10)
        return 0.0

    modes = ModeController(store, bus, probe=hang, degraded_max_latency_s=0.05)
    assert await modes.health_probe() == "OFFLINE"
    assert "timed out" in modes.last_reason


async def test_recovery_requires_a_streak(store, bus):
    flaky = [None, 0.2, None, 0.2, 0.2]

    async def probe():
        return flaky.pop(0)

    modes = ModeController(store, bus, probe=probe, recover_after=2)
    assert await modes.health_probe() == "OFFLINE"
    assert await modes.health_probe() == "OFFLINE"   # one good probe is not enough
    assert await modes.health_probe() == "OFFLINE"   # streak broken
    assert await modes.health_probe() == "OFFLINE"
    assert await modes.health_probe() == "FULL"


async def test_forced_mode_pins_everything(store, bus):
    modes = ModeController(store, bus, probe=lambda: 0.1, forced_mode="FULL")
    assert store.mode == "FULL"
    assert await modes.health_probe() == "FULL"
    modes.set_probe(lambda: None)
    assert await modes.health_probe() == "FULL"


async def test_mode_changed_is_not_re_emitted(store, bus):
    modes = ModeController(store, bus, probe=lambda: None)
    await modes.health_probe()
    await modes.health_probe()
    assert len(emitted(bus)) == 0    # already OFFLINE at boot, nothing changed


# ------------------------------------------------------------- scheduler


async def test_scheduler_jobs_are_registered(database, store, bus):
    jobs = BackgroundJobs(database, ModeController(store, bus), probe_interval_s=3600)
    jobs.start()
    try:
        assert {job["id"] for job in jobs.jobs()} >= {"health_probe", "prepare_next"}
    finally:
        jobs.shutdown()


async def test_default_seam_is_a_noop(database, store, bus):
    """The agent seam is defined, not imported: services/agent is a separate service."""
    jobs = BackgroundJobs(database, ModeController(store, bus))
    session_id = database.start_session(student_id="s01")
    database.record_observation("s01", "animal_vocab", "wrong", "chose dog for meow", session_id)

    assert await jobs.summarize_session(session_id) is None
    assert database.get_session_summary(session_id) is None
    assert await jobs.prepare_next() is None


async def test_injected_seam_writes_a_summary(database, store, bus):
    seen: dict = {}

    async def summarize(session_id: str, observations: list[dict]) -> dict:
        seen["observations"] = observations
        return {
            "summary": "Mixed up cat and dog sounds.",
            "weakPoints": ["animal_vocab"],
            "nextFocus": ["listening_a1"],
            "studentId": "s01",
            "skills": {"animal_vocab": 0.4},
        }

    jobs = BackgroundJobs(database, ModeController(store, bus))
    jobs.set_seam(AgentSeam(summarize_session=summarize, probe=lambda: 0.2))

    session_id = database.start_session(student_id="s01")
    database.upsert_student("s01", "Minh")
    database.record_observation("s01", "animal_vocab", "wrong", "chose dog for meow", session_id)
    database.end_session(session_id)

    result = await jobs.summarize_session(session_id)
    assert result["summary"] == "Mixed up cat and dog sounds."
    assert len(seen["observations"]) == 1
    assert database.get_session_summary(session_id)["weakPoints"] == ["animal_vocab"]
    assert database.get_student("s01")["skills"]["animal_vocab"] == 0.4
    # the summary is immediately recallable
    assert database.recall("cat and dog sounds")[0].text.startswith("Mixed up")
    # and the seam's probe is now what drives the mode
    assert jobs.modes.probe is not None


async def test_a_broken_seam_cannot_kill_the_scheduler(database, store, bus):
    async def explode(*args) -> dict:
        raise RuntimeError("agent exploded")

    jobs = BackgroundJobs(database, ModeController(store, bus))
    jobs.set_seam(AgentSeam(summarize_session=explode, prepare_next=explode))
    session_id = database.start_session()
    assert await jobs.summarize_session(session_id) is None
    assert await jobs.prepare_next({"classId": "demo"}) is None
    assert await jobs.health_probe() == "OFFLINE"


async def test_session_summary_is_scheduled_after_a_session_ends(database, store, bus):
    jobs = BackgroundJobs(database, ModeController(store, bus), summary_delay_s=30)
    session_id = database.start_session()
    jobs.schedule_session_summary(session_id)
    try:
        assert f"summarize_session:{session_id}" in {job["id"] for job in jobs.jobs()}
    finally:
        jobs.shutdown()
