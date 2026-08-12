"""Bridge from pytest to the Playwright scenarios in `tests/node/`.

playwright-core is a Node package (installed under `.tools/node_modules`), and
there is no Python Playwright in this environment -- so the browser work is
Node and the assertions come back as JSON. Each scenario prints exactly one
line of the form `@@RESULT@@ {json}` and this module parses it; anything the
scenario logs before that is kept in `tests/.artifacts/` for diagnosis.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .procs import ARTIFACTS, CHROME_PATH, TESTS_DIR, TOOLS_DIR

NODE_DIR = TESTS_DIR / "node"
RESULT_MARKER = "@@RESULT@@"


class BrowserError(RuntimeError):
    pass


def run_scenario(name: str, config: dict[str, Any], timeout: float = 180.0) -> dict[str, Any]:
    script = NODE_DIR / f"{name}.mjs"
    if not script.exists():
        raise BrowserError(f"no such browser scenario: {script}")
    if not CHROME_PATH.exists():
        raise BrowserError(
            f"chromium not found at {CHROME_PATH}; set BRIGHT_CHROME to override"
        )

    playwright = TOOLS_DIR / "node_modules" / "playwright-core" / "index.mjs"
    if not playwright.exists():
        raise BrowserError(f"playwright-core not found at {playwright}")

    env = dict(os.environ)
    # ESM resolution ignores NODE_PATH, so the package is handed over as an
    # absolute file URL rather than by adding a node_modules tree under tests/.
    env["PLAYWRIGHT_CORE"] = playwright.as_uri()
    env["CHROME_PATH"] = str(CHROME_PATH)
    env["BRIGHT_ARTIFACTS"] = str(ARTIFACTS)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["node", str(script), json.dumps(config)],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=str(TOOLS_DIR),
    )
    log = ARTIFACTS / f"browser-{name}.log"
    log.write_text(f"$ node {script}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")

    result: dict[str, Any] | None = None
    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_MARKER):
            result = json.loads(line[len(RESULT_MARKER) :].strip())
    if result is None:
        raise BrowserError(
            f"scenario {name} produced no result (exit {proc.returncode}).\n"
            f"stdout:\n{proc.stdout[-3000:]}\nstderr:\n{proc.stderr[-3000:]}"
        )
    result["_log"] = str(log)
    return result
