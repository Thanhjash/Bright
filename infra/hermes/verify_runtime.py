#!/usr/bin/env python3
"""Fail closed unless the installed runtime is the exact Bright wheel."""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import agent.bright_live as bright_live
from agent.bright_live import BRIGHT_PATCH_VERSION


EXPECTED = "0.20.0+bright.1"
MANIFEST = Path(__file__).with_name("manifest.json")


def main() -> int:
    installed = version("hermes-agent")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    installed_module = Path(bright_live.__file__).resolve()
    installed_sha = hashlib.sha256(installed_module.read_bytes()).hexdigest()
    expected_sha = manifest["bright_live_sha256"]
    if (
        installed != EXPECTED
        or BRIGHT_PATCH_VERSION != EXPECTED
        or installed_sha != expected_sha
    ):
        raise SystemExit(
            "Hermes runtime verification failed: "
            f"distribution={installed!r}, patch={BRIGHT_PATCH_VERSION!r}, "
            f"module_sha256={installed_sha!r}, expected={EXPECTED!r}/{expected_sha!r}"
        )
    print(f"verified hermes-agent {EXPECTED} ({installed_sha[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
