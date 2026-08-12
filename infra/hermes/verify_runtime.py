#!/usr/bin/env python3
"""Fail closed unless the installed runtime is Bright's distinct wheel."""

from importlib.metadata import version

from agent.bright_live import BRIGHT_PATCH_VERSION


EXPECTED = "0.20.0+bright.1"


def main() -> int:
    installed = version("hermes-agent")
    if installed != EXPECTED or BRIGHT_PATCH_VERSION != EXPECTED:
        raise SystemExit(
            "Hermes runtime verification failed: "
            f"distribution={installed!r}, patch={BRIGHT_PATCH_VERSION!r}, expected={EXPECTED!r}"
        )
    print(f"verified hermes-agent {EXPECTED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
