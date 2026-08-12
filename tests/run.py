#!/usr/bin/env python3
"""One command that runs the whole integration suite and prints the table.

    python3 tests/run.py                 everything
    python3 tests/run.py I1 I6           just those
    python3 tests/run.py --fast          skip the tests that play a lesson in
                                         real time (leaves I1, I2, I9 out)
    python3 tests/run.py --no-browser    skip anything needing Chromium
    python3 tests/run.py -k rapid        any pytest -k expression

Anything after `--` is passed straight to pytest.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

TEST_FILES = {
    "I1": "test_i1_lesson_without_agent.py",
    "I2": "test_i2_agent_killed_midlesson.py",
    "I3": "test_i3_reload_resnapshot.py",
    "I4": "test_i4_invalid_action_id.py",
    "I5": "test_i5_stale_state_version.py",
    "I6": "test_i6_act_token_split.py",
    "I7": "test_i7_rapid_interactions.py",
    "I8": "test_i8_memory_across_sessions.py",
    "I9": "test_i9_network_unplugged.py",
    "I10": "test_i10_feedback_latency.py",
}


def main() -> int:
    argv = sys.argv[1:]
    passthrough: list[str] = []
    if "--" in argv:
        idx = argv.index("--")
        passthrough = argv[idx + 1 :]
        argv = argv[:idx]

    marks: list[str] = []
    selected: list[str] = []
    extra: list[str] = []

    for arg in argv:
        upper = arg.upper()
        if upper in TEST_FILES:
            selected.append(TEST_FILES[upper])
        elif arg == "--fast":
            marks.append("not slow")
        elif arg == "--no-browser":
            marks.append("not browser")
        elif arg == "--browser-only":
            marks.append("browser")
        else:
            extra.append(arg)

    # Byte-code caching is disabled deliberately. The repo lives on a Windows
    # drive under WSL, where mtime granularity is coarse enough that an edited
    # module can match a stale `.pyc` -- which shows up as a test failing
    # against code that is no longer there.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    cmd = [sys.executable, "-m", "pytest"]
    cmd += selected or ["."]
    if marks:
        cmd += ["-m", " and ".join(marks)]
    cmd += extra + passthrough

    print(f"$ {' '.join(cmd)}\n", flush=True)
    return subprocess.run(cmd, cwd=str(HERE), env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
