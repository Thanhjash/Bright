#!/usr/bin/env python3
"""Fail closed unless the installed runtime is the exact Bright wheel."""

import hashlib
import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import agent.bright_live as bright_live
from agent.bright_live import BRIGHT_PATCH_VERSION


MANIFEST = Path(__file__).with_name("manifest.json")


def main() -> int:
    installed = version("hermes-agent")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = manifest["version"]
    installed_module = Path(bright_live.__file__).resolve()
    installed_sha = hashlib.sha256(installed_module.read_bytes()).hexdigest()
    expected_sha = manifest["bright_live_sha256"]
    if (
        installed != expected
        or BRIGHT_PATCH_VERSION != expected
        or installed_sha != expected_sha
    ):
        raise SystemExit(
            "Hermes runtime verification failed: "
            f"distribution={installed!r}, patch={BRIGHT_PATCH_VERSION!r}, "
            f"module_sha256={installed_sha!r}, expected={expected!r}/{expected_sha!r}"
        )
    # The module entrypoint—not pip's console-script wrapper—is Bright's
    # launch contract. Exercise it with the exact interpreter that imported
    # the installed package.
    for args in (
        (sys.executable, "-m", "hermes_cli.main", "--version"),
        (sys.executable, "-m", "hermes_cli.main", "gateway", "run", "--help"),
    ):
        subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    print(f"verified hermes-agent {expected} ({installed_sha[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
