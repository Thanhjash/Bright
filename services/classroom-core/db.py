"""SQLite persistence -- schema per docs/archive/phase-1-plan.md §5.

Learning state (``students``, ``skills``), episodic memory (``sessions``,
``observations``) and teacher long-term memory (``session_summaries``), with an
FTS5 index (``memories_fts``) over observation evidence + summary text.

``recall()`` is the query side of the ``classroom_recall`` tool: FTS5 MATCH
scored with bm25 and re-weighted by recency.  No vector DB in Phase 1.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import config  # noqa: F401  -- installs the bright_contracts import path
from bright_contracts import RecalledMemory

RECALL_HALF_LIFE_DAYS = 14.0
RECALL_RECENCY_FLOOR = 0.25   # a very old but perfect match still scores this
_TOKEN_RE = re.compile(r"[0-9A-Za-z_À-ɏḀ-ỿ']+")

MIGRATIONS: list[tuple[str, tuple[str, ...]]] = [
    (
        "0001_initial",
        (
            """
            CREATE TABLE IF NOT EXISTS students (
                id           TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                display_name TEXT,
                created_at   TEXT NOT NULL,
                meta_json    TEXT NOT NULL DEFAULT '{}'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS skills (
                student_id TEXT NOT NULL,
                skill      TEXT NOT NULL,
                estimate   REAL NOT NULL DEFAULT 0.0,
                confidence REAL NOT NULL DEFAULT 0.0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (student_id, skill)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                student_id TEXT,
                started_at TEXT NOT NULL,
                ended_at   TEXT,
                lesson_id  TEXT,
                mode       TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS observations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                student_id TEXT,
                skill      TEXT,
                result     TEXT,
                evidence   TEXT,
                ts         TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS session_summaries (
                session_id       TEXT PRIMARY KEY,
                summary          TEXT NOT NULL,
                weak_points_json TEXT NOT NULL DEFAULT '[]',
                next_focus_json  TEXT NOT NULL DEFAULT '[]',
                created_at       TEXT NOT NULL
            )
            """,
            # Only `text` is indexed -- metadata columns are UNINDEXED so a
            # query like "s17" cannot match on an id and fake a hit.
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                text,
                kind       UNINDEXED,
                ref_id     UNINDEXED,
                student_id UNINDEXED,
                epoch      UNINDEXED,
                tokenize = 'porter unicode61'
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_obs_session ON observations(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_obs_student ON observations(student_id, ts)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_student ON sessions(student_id, started_at)",
        ),
    ),
    (
        "0002_class_session_controller",
        (
            "ALTER TABLE observations ADD COLUMN response_turn_id TEXT",
            "ALTER TABLE observations ADD COLUMN activity_id TEXT",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_obs_response_skill
            ON observations(session_id, response_turn_id, skill)
            WHERE response_turn_id IS NOT NULL
            """,
            """
            CREATE TABLE IF NOT EXISTS session_checkpoints (
                session_id          TEXT PRIMARY KEY,
                decision_revision   INTEGER NOT NULL,
                activity_id         TEXT,
                activity_generation INTEGER NOT NULL,
                session_state       TEXT NOT NULL,
                snapshot_json       TEXT NOT NULL,
                updated_at          TEXT NOT NULL
            )
            """,
        ),
    ),
    (
        "0003_class_participation",
        (
            """
            CREATE TABLE IF NOT EXISTS session_participants (
                session_id   TEXT NOT NULL,
                learner_id   TEXT NOT NULL,
                display_name TEXT NOT NULL,
                seat         TEXT,
                present      INTEGER NOT NULL,
                scheduled    INTEGER NOT NULL DEFAULT 0,
                attempted    INTEGER NOT NULL DEFAULT 0,
                responded    INTEGER NOT NULL DEFAULT 0,
                evidenced    INTEGER NOT NULL DEFAULT 0,
                skipped      INTEGER NOT NULL DEFAULT 0,
                last_event   TEXT,
                updated_at   TEXT NOT NULL,
                PRIMARY KEY (session_id, learner_id)
            )
            """,
        ),
    ),
    (
        "0004_observation_mode",
        (
            "ALTER TABLE observations ADD COLUMN mode TEXT",
        ),
    ),
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).isoformat(timespec="seconds")


def fts_query(raw: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression.

    Tokens are quoted (so punctuation, ``"`` and FTS operators cannot escape)
    and OR-joined -- recall should be forgiving, ranking sorts it out.
    """
    tokens = _TOKEN_RE.findall(raw or "")[:16]
    tokens = [t.replace('"', "") for t in tokens if t]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


class Database:
    """Thin, thread-safe wrapper over one sqlite3 connection."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path not in (":memory:", ""):
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            if self.path not in (":memory:", ""):
                self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")

    # ---------------------------------------------------------- migrations
    def migrate(self) -> list[str]:
        """Run pending migrations. Idempotent -- safe on every startup."""
        applied: list[str] = []
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            done = {
                row["id"] for row in self._conn.execute("SELECT id FROM schema_migrations")
            }
            self._conn.commit()
            for migration_id, statements in MIGRATIONS:
                if migration_id in done:
                    continue
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                    for statement in statements:
                        self._conn.execute(statement)
                    self._conn.execute(
                        "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
                        (migration_id, iso()),
                    )
                    self._conn.commit()
                    applied.append(migration_id)
                except Exception:
                    self._conn.rollback()
                    raise
        return applied

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -------------------------------------------------------------- students
    def upsert_student(
        self,
        student_id: str,
        name: str,
        display_name: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO students (id, name, display_name, created_at, meta_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    display_name = COALESCE(excluded.display_name, students.display_name),
                    meta_json = excluded.meta_json
                """,
                (student_id, name, display_name, iso(), json.dumps(meta or {})),
            )
            self._conn.commit()
        return self.get_student(student_id)  # type: ignore[return-value]

    def get_student(self, student_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM students WHERE id = ?", (student_id,)
            ).fetchone()
            if row is None:
                return None
            skills = self._conn.execute(
                "SELECT skill, estimate, confidence, updated_at FROM skills WHERE student_id = ?",
                (student_id,),
            ).fetchall()
        return {
            "id": row["id"],
            "name": row["name"],
            "displayName": row["display_name"],
            "createdAt": row["created_at"],
            "meta": json.loads(row["meta_json"] or "{}"),
            "skills": {s["skill"]: s["estimate"] for s in skills},
            "skillDetail": [dict(s) for s in skills],
        }

    def update_skill(
        self,
        student_id: str,
        skill: str,
        estimate: float,
        confidence: float = 0.5,
    ) -> dict[str, Any]:
        estimate = max(0.0, min(1.0, float(estimate)))
        confidence = max(0.0, min(1.0, float(confidence)))
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO skills (student_id, skill, estimate, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(student_id, skill) DO UPDATE SET
                    estimate = excluded.estimate,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at
                """,
                (student_id, skill, estimate, confidence, iso()),
            )
            self._conn.commit()
        return {
            "studentId": student_id,
            "skill": skill,
            "estimate": estimate,
            "confidence": confidence,
        }

    # -------------------------------------------------------------- sessions
    def start_session(
        self,
        student_id: str | None = None,
        lesson_id: str | None = None,
        mode: str = "OFFLINE",
        session_id: str | None = None,
    ) -> str:
        session_id = session_id or uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (id, student_id, started_at, ended_at, lesson_id, mode)"
                " VALUES (?, ?, ?, NULL, ?, ?)",
                (session_id, student_id, iso(), lesson_id, mode),
            )
            self._conn.commit()
        return session_id

    def end_session(self, session_id: str, mode: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            if mode is None:
                self._conn.execute(
                    "UPDATE sessions SET ended_at = ? WHERE id = ?", (iso(), session_id)
                )
            else:
                self._conn.execute(
                    "UPDATE sessions SET ended_at = ?, mode = ? WHERE id = ?",
                    (iso(), mode, session_id),
                )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_open_sessions(self, student_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE student_id = ? AND ended_at IS NULL "
                "ORDER BY started_at ASC",
                (student_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ---------------------------------------------------------- observations
    def record_observation(
        self,
        student_id: str | None,
        skill: str,
        result: str,
        evidence: str,
        session_id: str | None = None,
        ts: datetime | None = None,
        *,
        response_turn_id: str | None = None,
        activity_id: str | None = None,
        mode: str | None = None,
    ) -> int:
        when = ts or utc_now()
        stored_mode = (mode or "").strip() or None
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO observations "
                "(session_id, student_id, skill, result, evidence, ts, response_turn_id, activity_id, mode)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    student_id,
                    skill,
                    result,
                    evidence,
                    iso(when),
                    response_turn_id,
                    activity_id,
                    stored_mode,
                ),
            )
            inserted = cur.rowcount != 0
            if inserted:
                obs_id = int(cur.lastrowid or 0)
            elif response_turn_id is not None:
                row = self._conn.execute(
                    "SELECT id FROM observations WHERE session_id IS ? "
                    "AND response_turn_id = ? AND skill = ?",
                    (session_id, response_turn_id, skill),
                ).fetchone()
                obs_id = int(row["id"]) if row else 0
            else:
                obs_id = 0
            if inserted:
                self._index_memory(
                    text=f"{skill} {result}: {evidence}",
                    kind="observation",
                    ref_id=str(obs_id),
                    student_id=student_id,
                    when=when,
                )
            self._conn.commit()
        return obs_id

    def save_session_checkpoint(
        self,
        *,
        session_id: str,
        decision_revision: int,
        activity_id: str | None,
        activity_generation: int,
        session_state: str,
        snapshot: dict[str, Any],
    ) -> None:
        """Durably replace the one resumable controller checkpoint."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    """
                    INSERT INTO session_checkpoints (
                        session_id, decision_revision, activity_id,
                        activity_generation, session_state, snapshot_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        decision_revision = excluded.decision_revision,
                        activity_id = excluded.activity_id,
                        activity_generation = excluded.activity_generation,
                        session_state = excluded.session_state,
                        snapshot_json = excluded.snapshot_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session_id,
                        decision_revision,
                        activity_id,
                        activity_generation,
                        session_state,
                        json.dumps(snapshot, separators=(",", ":"), sort_keys=True),
                        iso(),
                    ),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def get_session_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM session_checkpoints WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["snapshot"] = json.loads(result.pop("snapshot_json") or "{}")
        return result

    def replace_session_participants(
        self, session_id: str, participants: list[dict[str, Any]]
    ) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for item in participants:
                    self._conn.execute(
                        """
                        INSERT INTO session_participants (
                            session_id, learner_id, display_name, seat, present, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(session_id, learner_id) DO UPDATE SET
                            display_name = excluded.display_name,
                            seat = excluded.seat,
                            present = excluded.present,
                            updated_at = excluded.updated_at
                        """,
                        (
                            session_id,
                            item["learner_id"],
                            item["display_name"],
                            item.get("seat"),
                            int(bool(item.get("present"))),
                            iso(),
                        ),
                    )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def update_session_participation(
        self,
        *,
        session_id: str,
        learner_id: str,
        scheduled: int,
        attempted: int,
        responded: int,
        evidenced: int,
        skipped: int,
        event: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE session_participants SET
                    scheduled = ?, attempted = ?, responded = ?, evidenced = ?,
                    skipped = ?, last_event = ?, updated_at = ?
                WHERE session_id = ? AND learner_id = ?
                """,
                (
                    scheduled,
                    attempted,
                    responded,
                    evidenced,
                    skipped,
                    event,
                    iso(),
                    session_id,
                    learner_id,
                ),
            )
            self._conn.commit()

    def list_session_participants(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM session_participants WHERE session_id = ? ORDER BY learner_id",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_observations(
        self, session_id: str | None = None, student_id: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        clauses, params = [], []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if student_id:
            clauses.append("student_id = ?")
            params.append(student_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM observations {where} ORDER BY id ASC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ summaries
    def write_session_summary(
        self,
        session_id: str,
        summary: str,
        weak_points: Iterable[str] = (),
        next_focus: Iterable[str] = (),
        ts: datetime | None = None,
    ) -> dict[str, Any]:
        when = ts or utc_now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO session_summaries
                    (session_id, summary, weak_points_json, next_focus_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary = excluded.summary,
                    weak_points_json = excluded.weak_points_json,
                    next_focus_json = excluded.next_focus_json,
                    created_at = excluded.created_at
                """,
                (
                    session_id,
                    summary,
                    json.dumps(list(weak_points)),
                    json.dumps(list(next_focus)),
                    iso(when),
                ),
            )
            self._conn.execute(
                "DELETE FROM memories_fts WHERE kind = 'summary' AND ref_id = ?", (session_id,)
            )
            row = self._conn.execute(
                "SELECT student_id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            self._index_memory(
                text=summary,
                kind="summary",
                ref_id=session_id,
                student_id=row["student_id"] if row else None,
                when=when,
            )
            self._conn.commit()
        return {
            "sessionId": session_id,
            "summary": summary,
            "weakPoints": list(weak_points),
            "nextFocus": list(next_focus),
        }

    def get_session_summary(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM session_summaries WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "sessionId": row["session_id"],
            "summary": row["summary"],
            "weakPoints": json.loads(row["weak_points_json"] or "[]"),
            "nextFocus": json.loads(row["next_focus_json"] or "[]"),
            "createdAt": row["created_at"],
        }

    # --------------------------------------------------------------- recall
    def _index_memory(
        self,
        text: str,
        kind: str,
        ref_id: str,
        student_id: str | None,
        when: datetime,
    ) -> None:
        self._conn.execute(
            "INSERT INTO memories_fts (text, kind, ref_id, student_id, epoch)"
            " VALUES (?, ?, ?, ?, ?)",
            (text, kind, ref_id, student_id or "", f"{when.timestamp():.3f}"),
        )

    def recall(
        self,
        query: str,
        k: int = 5,
        student_id: str | None = None,
        kind: str | None = None,
    ) -> list[RecalledMemory]:
        """FTS5 MATCH, bm25-ranked, re-weighted by recency.

        ``kind`` restricts to one memory tier -- ``observation`` (episodic) or
        ``summary`` (teacher long-term).  Needed because bm25 rewards short
        documents, so a one-line observation row will out-rank the session
        summary written *about* it every time, and a caller that wants the
        durable note has no other way to ask for it.
        """
        match = fts_query(query)
        if not match:
            return []
        params: list[Any] = [match]
        extra = ""
        if student_id:
            extra += " AND student_id = ?"
            params.append(student_id)
        if kind:
            extra += " AND kind = ?"
            params.append(kind)
        params.append(max(k, 1) * 8)
        with self._lock:
            try:
                rows = self._conn.execute(
                    "SELECT text, kind, epoch, bm25(memories_fts) AS score"
                    " FROM memories_fts WHERE memories_fts MATCH ?"
                    f"{extra} ORDER BY score LIMIT ?",
                    params,
                ).fetchall()
            except sqlite3.OperationalError:
                return []

        now = time.time()
        scored: list[tuple[float, float, str]] = []
        for row in rows:
            relevance = -float(row["score"])          # bm25: more negative == better
            try:
                epoch = float(row["epoch"])
            except (TypeError, ValueError):
                epoch = now
            age_days = max(0.0, (now - epoch) / 86400.0)
            recency = math.pow(0.5, age_days / RECALL_HALF_LIFE_DAYS)
            weight = RECALL_RECENCY_FLOOR + (1.0 - RECALL_RECENCY_FLOOR) * recency
            scored.append((relevance * weight, epoch, row["text"]))

        scored.sort(key=lambda item: (-item[0], -item[1]))
        out: list[RecalledMemory] = []
        for _score, epoch, text in scored[:k]:
            when = datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat()
            out.append(RecalledMemory(text=text, when=when))
        return out


def open_database(path: str | Path) -> Database:
    """Open + migrate. Call once at startup."""
    database = Database(path)
    database.migrate()
    return database


__all__ = ["Database", "open_database", "fts_query", "MIGRATIONS", "utc_now", "iso"]
