"""Fixtures and the pass/fail table.

Everything a test touches is a real process on a port the demo does not use.
Session-scoped fixtures are plain synchronous objects that manage subprocesses,
so pytest-asyncio never has to reconcile loop scopes -- the only asynchronous
things in the suite are the WebSocket clients, and those are per-test.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import ARTIFACTS, Core, FakeLLM, FakeTTS, TcpProxy, Ui  # noqa: E402
from harness.net import free_port  # noqa: E402
from harness.procs import TESTS_DIR  # noqa: E402

# ---------------------------------------------------------------- the marker


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "itest(id, title, gate=False): tag a test with its integration-plan id (I1-I10)",
    )
    config.addinivalue_line("markers", "browser: needs a real Chromium and the UI dev server")
    config.addinivalue_line("markers", "slow: plays a lesson in real time")


# ------------------------------------------------------------------ the stack


class Stack:
    """Every long-lived process the suite needs, and the wiring between them.

                     ┌──────────── fake TTS ◄── the UI's speech pipeline
      browser ──► UI ─┤                          (I6 reads what it was asked to say)
                      └── TCP proxy ──► core ──► fake LLM  ("the agent")
                            (I9 cuts this)        (I2 kills this)
    """

    def __init__(self) -> None:
        self.tts = FakeTTS()
        self.llm = FakeLLM()
        self.core = Core(data_name="main")
        self.proxy: TcpProxy | None = None      # browser ↔ core
        self.llm_proxy: TcpProxy | None = None  # core ↔ model endpoint
        self.ui: Ui | None = None
        self._ui_port = free_port()

    # ---------------------------------------------------------------- start

    def start(self) -> "Stack":
        self.tts.start()
        self.llm.start()
        self.proxy = TcpProxy(target_port=self.core.port).start()
        self.llm_proxy = TcpProxy(target_port=self.llm.port).start()
        self.start_core(wipe=True)
        return self

    @property
    def llm_url(self) -> str:
        """Core reaches the model through a cuttable link, so I9 can unplug it."""
        assert self.llm_proxy is not None
        return f"http://127.0.0.1:{self.llm_proxy.port}/v1"

    def start_core(self, *, agent: bool = True, wipe: bool = False) -> None:
        self.core.start(
            agent=agent,
            llm_base_url=self.llm_url,
            wipe=wipe,
            ui_origin=f"http://127.0.0.1:{self._ui_port}",
        )

    def restart_core(self, *, agent: bool = True, wipe: bool = False) -> None:
        self.core.stop()
        self.start_core(agent=agent, wipe=wipe)

    def ensure_ui(self) -> Ui:
        if self.ui is None:
            assert self.proxy is not None
            ui = Ui(port=self._ui_port)
            ui.start(
                bus_url=f"ws://127.0.0.1:{self.proxy.port}/ws",
                core_http=f"http://127.0.0.1:{self.proxy.port}",
                speech_url=self.tts.base_url,
            )
            self.ui = ui
        return self.ui

    def restart_llm(self) -> None:
        """Bring the model endpoint back after a test kills it."""
        if not self.llm.alive():
            self.llm = FakeLLM(port=self.llm.port)
            self.llm.start()

    def stop(self) -> None:
        for proc in (self.ui, self.core, self.llm, self.tts):
            if proc is not None:
                try:
                    proc.stop()
                except Exception:  # noqa: BLE001
                    pass
        for prox in (self.proxy, self.llm_proxy):
            if prox is not None:
                prox.stop()


@pytest.fixture(scope="session")
def stack() -> Any:
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS, ignore_errors=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    s = Stack().start()
    try:
        yield s
    finally:
        s.stop()


@pytest.fixture
def core(stack: Stack) -> Any:
    """A healthy core with the agent wired to the scripted model.

    Restored between tests: a previous test may have killed the model endpoint
    or left the runner mid-lesson.
    """
    stack.restart_llm()
    if stack.llm_proxy is not None:
        stack.llm_proxy.restore()
    if not stack.core.alive():
        stack.start_core()
    # Reset everything a previous test could have left behind: a pinned mode
    # (which decides whether the decision gate runs at all) and a scripted
    # model reply (which would then drive an unrelated test's lesson).
    try:
        stack.core.set_mode("OFFLINE", "reset between tests")
        stack.llm.script([{"chunks": [{"content": "ok"}], "finish": "stop"}],
                         non_stream={"content": "ok", "status": 200, "delay_before_s": 0.0})
    except Exception:  # noqa: BLE001
        pass
    yield stack.core
    try:
        stack.core.control("pause")
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def llm(stack: Stack) -> Any:
    stack.restart_llm()
    return stack.llm


@pytest.fixture
def tts(stack: Stack) -> Any:
    stack.tts.reset()
    return stack.tts


@pytest.fixture
def proxy(stack: Stack) -> Any:
    """The browser ↔ core link."""
    assert stack.proxy is not None
    yield stack.proxy
    stack.proxy.restore()


@pytest.fixture
def llm_link(stack: Stack) -> Any:
    """The core ↔ model link — the project's one outbound host."""
    assert stack.llm_proxy is not None
    yield stack.llm_proxy
    stack.llm_proxy.restore()


@pytest.fixture(scope="session")
def ui(stack: Stack) -> Any:
    return stack.ensure_ui()


@pytest.fixture
def probing_core(stack: Stack) -> Any:
    """A core that actually probes, for the one test about the probe.

    Everything else runs with probing effectively disabled so the mode is a
    test input rather than a race.
    """
    c = Core(data_name="probing")
    stack.restart_llm()
    c.start(
        agent=True,
        llm_base_url=stack.llm_url,
        wipe=True,
        extra_env={"CORE_PROBE_INTERVAL_S": "3"},
    )
    try:
        yield c
    finally:
        c.stop()


@pytest.fixture
def speech_drag_core(stack: Stack) -> Any:
    """A core playing a lesson whose answers are `speech` and `drag`.

    The sample lesson only grades `choice`, so the code paths for the other two
    answer kinds have never been exercised end to end. `tests/fixtures/` owns
    this lesson; nothing under `content/` or `services/` is touched.
    """
    c = Core(data_name="answerkinds")
    stack.restart_llm()
    c.start(
        agent=True,
        llm_base_url=stack.llm_url,
        wipe=True,
        extra_env={
            "CORE_LESSON_RUN": str(TESTS_DIR / "fixtures" / "lesson_answer_kinds.json"),
            "CORE_SILENCE_TIMEOUT_S": "30",
        },
    )
    try:
        yield c
    finally:
        c.stop()


@pytest.fixture
def memory_core(stack: Stack) -> Any:
    """A core with its own database, restartable between the two sessions.

    I8's claim is that memory survives the bell, so the second session must run
    in a process that did not hold the first one's state in RAM.
    """
    c = Core(data_name="memory")
    stack.restart_llm()
    probe_env = {"CORE_PROBE_INTERVAL_S": "2"}   # the greeting only runs in FULL
    c.start(agent=True, llm_base_url=stack.llm_url, wipe=True, extra_env=probe_env)

    def restart() -> None:
        c.stop()
        c.start(agent=True, llm_base_url=stack.llm_url, wipe=False, extra_env=probe_env)

    c.restart_same_data = restart  # type: ignore[attr-defined]
    try:
        yield c
    finally:
        c.stop()


@pytest.fixture
def solo_core() -> Any:
    """A core with **no agent at all** -- the NS-1 configuration.

    Not the shared `core` fixture with the model unplugged: NS-1's claim is
    that the lesson runs when there is nothing to unplug, so `BRIGHT_AGENT` is
    never set and no agent object is ever constructed.
    """
    c = Core(data_name="solo")
    c.start(agent=False, wipe=True)
    try:
        yield c
    finally:
        c.stop()


# ------------------------------------------------------------- result table

_RESULTS: dict[str, dict[str, Any]] = {}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: Any):
    outcome = yield
    report = outcome.get_result()
    marker = item.get_closest_marker("itest")
    if marker is None:
        return
    test_id = marker.kwargs.get("id") or (marker.args[0] if marker.args else "?")
    title = marker.kwargs.get("title") or (marker.args[1] if len(marker.args) > 1 else "")
    gate = bool(marker.kwargs.get("gate"))
    entry = _RESULTS.setdefault(
        test_id,
        {"title": title, "gate": gate, "status": "pass", "duration": 0.0, "failures": []},
    )
    if title and not entry["title"]:
        entry["title"] = title
    entry["gate"] = entry["gate"] or gate

    if report.when == "call":
        entry["duration"] += report.duration
    if report.outcome == "failed":
        entry["status"] = "fail"
        entry["failures"].append(f"{item.name} ({report.when})")
    elif report.outcome == "skipped" and entry["status"] == "pass":
        entry["status"] = "skip"
        entry["failures"].append(f"{item.name} skipped")


def _order_key(test_id: str) -> tuple[int, str]:
    digits = "".join(ch for ch in test_id if ch.isdigit())
    return (int(digits) if digits else 99, test_id)


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    if not _RESULTS:
        return
    tw = terminalreporter
    tw.write_sep("=", "BRIGHT INTEGRATION SUITE")
    tw.write_line("")
    tw.write_line(f"{'ID':<5} {'GATE':<5} {'RESULT':<7} {'TIME':>7}  WHAT IT PROTECTS")
    tw.write_line("-" * 100)
    gates_failed = []
    for test_id in sorted(_RESULTS, key=_order_key):
        entry = _RESULTS[test_id]
        status = entry["status"].upper()
        colour = {"PASS": {"green": True}, "FAIL": {"red": True}, "SKIP": {"yellow": True}}[status]
        gate = "GATE" if entry["gate"] else ""
        if entry["gate"] and status != "PASS":
            gates_failed.append(test_id)
        tw.write(f"{test_id:<5} {gate:<5} ")
        tw.write(f"{status:<7}", **colour)
        tw.write_line(f" {entry['duration']:>6.1f}s  {entry['title']}")
        for failure in entry["failures"]:
            tw.write_line(f"{'':<19}     ↳ {failure}")
    tw.write_line("-" * 100)
    passed = sum(1 for e in _RESULTS.values() if e["status"] == "pass")
    tw.write_line(f"{passed}/{len(_RESULTS)} integration tests pass")
    if gates_failed:
        tw.write_line(f"RELEASE GATES FAILING: {', '.join(sorted(gates_failed, key=_order_key))}", red=True)
    else:
        tw.write_line("all release gates green", green=True)
    tw.write_line(f"artifacts: {ARTIFACTS}")
