from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import config  # noqa: E402,F401  -- installs the bright_contracts import path
from bright_contracts import (  # noqa: E402
    Activity,
    Branch,
    Expect,
    LessonRun,
    Narration,
    TurnContext,
)
from bus import EventBus  # noqa: E402
from db import open_database  # noqa: E402
from runner import LessonRunner, load_lesson_run  # noqa: E402
from state import StateStore  # noqa: E402

SAMPLE_LESSON_PATH = ROOT / "data" / "sample_lesson_run.json"


@pytest.fixture
def store() -> StateStore:
    return StateStore(mode="OFFLINE")


@pytest.fixture
def bus(store: StateStore) -> EventBus:
    return EventBus(lambda: store.state_version, queue_maxsize=8)


@pytest.fixture
def database(tmp_path: Path):
    db = open_database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def sample_lesson() -> LessonRun:
    return load_lesson_run(str(SAMPLE_LESSON_PATH))


@pytest.fixture
def tiny_lesson() -> LessonRun:
    """Fast synthetic run: 1-second timers, one branch point, one silence point."""
    return LessonRun(
        lessonId="tiny-01",
        classId="test",
        title="Tiny",
        focus=["animal_vocab"],
        activities=[
            Activity(
                id="a1",
                scene="text",
                props={"text": "hello"},
                narration=[Narration(text="hello there")],
                durationS=1,
            ),
            Activity(
                id="a2",
                scene="choice",
                props={
                    "prompt": "which?",
                    "options": [{"id": "x", "text": "x"}, {"id": "y", "text": "y"}],
                },
                durationS=1,
                expect=Expect(kind="choice", correct="x", acceptFuzzy=["y"]),
                branches=[
                    Branch(on="correct", goto="a3", narration=[Narration(text="yes!")]),
                    Branch(on="near", goto="a3"),
                    Branch(on="wrong", goto="a4"),
                    Branch(on="silence", goto="a4"),
                    Branch(on="timeout", goto="a4"),
                ],
            ),
            Activity(id="a3", scene="text", props={"text": "well done"}),
            Activity(id="a4", scene="text", props={"text": "let us retry"}),
            Activity(
                id="a5",
                scene="text",
                props={"text": "say it"},
                expect=Expect(kind="speech", correct=["i like cats"], acceptFuzzy=["i like cat"]),
                branches=[
                    Branch(on="correct", goto="a3"),
                    Branch(on="wrong", goto="a4"),
                    Branch(on="silence", goto="a4"),
                ],
            ),
        ],
    )


@pytest.fixture
def runner(bus: EventBus, store: StateStore, tiny_lesson: LessonRun) -> LessonRunner:
    return LessonRunner(
        bus, store, tiny_lesson, silence_timeout_s=0.05, reveal_hold_s=0.0
    )


# ------------------------------------------------------------- agent fakes
#
# No test may reach the network. `AgentDriver` takes an agent *factory*, and
# `take_turn` only ever reads `event.type` / `.reason` / `.usage` off whatever
# the agent yields, so a scripted async generator is a complete stand-in for
# `DirectAgent` -- including its `complete()` half, which the background
# summariser uses.


class ScriptedAgent:
    """A `TeacherAgent`-shaped fake: scripted tool calls, no model.

    ``script(ctx)`` returns the ``(tool, arguments)`` pairs this turn should
    make. Arguments may be a callable so a test can quote the live
    ``state_version``.
    """

    def __init__(
        self,
        executor: Callable[..., Any],
        script: Callable[[TurnContext], list[tuple[str, Any]]],
        *,
        delay: float = 0.0,
        reply: str | None = None,
        complete_error: Exception | None = None,
    ) -> None:
        self.executor = executor
        self.script = script
        self.delay = delay
        #: What `complete()` returns as message content -- the summariser half.
        self.reply = reply
        self.complete_error = complete_error
        self.contexts: list[TurnContext] = []
        self.completions: list[list[dict[str, Any]]] = []
        #: Every (tool, result) pair core handed back, so a test can inspect
        #: what the model would actually have seen mid-turn.
        self.results: list[tuple[str, Any]] = []
        self.started = 0
        self.in_flight = 0
        self.max_in_flight = 0

    async def turn(self, ctx: TurnContext):
        self.contexts.append(ctx)
        self.started += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            for name, args in self.script(ctx):
                result = await self.executor(name, args(ctx) if callable(args) else args)
                self.results.append((name, result))
                yield SimpleNamespace(type="tool_result")
            yield SimpleNamespace(type="done", reason="complete", usage=None)
        finally:
            self.in_flight -= 1

    async def complete(
        self, messages: list[dict[str, Any]], **_kwargs: Any
    ) -> dict[str, Any]:
        self.completions.append(messages)
        if self.complete_error is not None:
            raise self.complete_error
        return {"choices": [{"message": {"content": self.reply or ""}}]}


def choose(action_id: str, **params: Any):
    """Script one `classroom_choose_next` against the live state_version."""

    def build(ctx: TurnContext) -> list[tuple[str, Any]]:
        args: dict[str, Any] = {"action_id": action_id, "state_version": ctx.state_version}
        if params:
            args["params"] = params
        return [("classroom_choose_next", args)]

    return build


def nothing(_ctx: TurnContext) -> list[tuple[str, Any]]:
    """A turn that speaks to nobody and decides nothing."""
    return []


def wire(core: Any, script, **kwargs: Any) -> ScriptedAgent:
    """Attach a scripted agent to a Core, the way app.py attaches the real one."""
    from agent_bridge import AgentDriver

    made: dict[str, ScriptedAgent] = {}

    def factory(executor):
        made["agent"] = ScriptedAgent(executor, script, **kwargs)
        return made["agent"]

    core.set_agent_driver(AgentDriver(core, factory))
    return made["agent"]


def write_lesson(path: Path, lesson: LessonRun) -> Path:
    path.write_text(
        json.dumps(lesson.model_dump(by_alias=True, mode="json", exclude_none=True)),
        encoding="utf-8",
    )
    return path


@pytest.fixture
async def core(tmp_path: Path, tiny_lesson: LessonRun):
    """A whole `Core`, on a real (temporary) database, pinned to FULL.

    Async so teardown happens *inside* the test's event loop: ending a session
    starts apscheduler's AsyncIOScheduler on that loop, and shutting it down
    from a sync finaliser reaches a loop that is already closed.
    """
    from app import build_core
    from config import Settings

    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "core.db",
        lesson_run_path=write_lesson(tmp_path / "tiny_lesson_run.json", tiny_lesson),
        silence_timeout_s=0.05,
        reveal_hold_s=0.0,
        mode_override="FULL",
        agent_turn_timeout_s=0.5,
        agent_greeting_timeout_s=0.5,
        # Most memory-loop tests exercise the future local-model behaviour
        # (recognise a learner by name and recall their own notes). Dedicated
        # hosted-policy tests opt into hosted-minimal explicitly.
        agent_context_policy="local-trusted",
        probe_interval_s=3600,
    )
    built = build_core(settings)
    yield built
    if built.runner is not None:
        await built.runner.stop()
    built.jobs.shutdown()
    built.db.close()
