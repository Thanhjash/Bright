"""Test bootstrap.

`packages/contracts/python` is not an installable distribution yet, so put
it on the path here rather than copying the models (which the contract
forbids). Also loads `.env` for the `live` tests — the key is never
hardcoded and never committed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
CONTRACTS = REPO_ROOT / "packages" / "contracts" / "python"

for p in (HERE, CONTRACTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader — no extra dependency. Never overrides a real env var."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and not os.environ.get(key):
            os.environ[key] = value


_load_dotenv(REPO_ROOT / ".env")
