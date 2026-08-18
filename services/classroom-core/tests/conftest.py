from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import config  # noqa: E402,F401  -- installs the bright_contracts import path
from bus import EventBus  # noqa: E402
from db import open_database  # noqa: E402
from state import StateStore  # noqa: E402


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
