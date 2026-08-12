"""Make `bright_contracts` importable when nobody bootstrapped the path.

`packages/contracts/python` is not an installable distribution yet. Inside
pytest, `services/agent/conftest.py` puts it on `sys.path`; inside
classroom-core, `config.py` does. But `python -m bright_agent.preflight`
has neither, and a preflight that cannot even import is useless the one
morning it matters.

Strictly a no-op when the import already works. It never touches `.env`
and never overrides anything — reading configuration is `LLMConfig`'s job.
"""

from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path


def ensure_contracts_on_path() -> None:
    try:
        if find_spec("bright_contracts") is not None:
            return
    except (ImportError, ValueError):  # pragma: no cover - defensive
        pass
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / "packages" / "contracts" / "python"
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


__all__ = ["ensure_contracts_on_path"]
