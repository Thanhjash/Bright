from __future__ import annotations

import math
import sqlite3
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence

import os

# Beside the classroom database, not inside it: biometric templates are
# their own kind of data and their own deletion story (NORTH-STAR rule 2).
FACE_DB = Path(os.environ.get("FACE_DB", Path(__file__).resolve().parents[2] / "data" / "faces.db"))



@dataclass(frozen=True)
class FaceMatch:
    subject_id: str
    display_name: str
    similarity: float


def _normalize(values: Iterable[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if not vector:
        raise ValueError("Face embedding cannot be empty")
    if any(not math.isfinite(value) for value in vector):
        raise ValueError("Face embedding must contain only finite numbers")
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        raise ValueError("Face embedding cannot be a zero vector")
    return tuple(value / magnitude for value in vector)


def _pack(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack(blob: bytes, dimension: int) -> tuple[float, ...]:
    if len(blob) != dimension * 4:
        raise ValueError("Stored face embedding has an invalid byte length")
    return struct.unpack(f"<{dimension}f", blob)


class FaceEmbeddingStore:
    """Local SQLite store for consented face embeddings, never raw photos."""

    def __init__(self, path: Path | None = None):
        path = Path(path) if path else FACE_DB
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS subjects (
                    subject_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    consent_reference TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS face_embeddings (
                    embedding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    dimension INTEGER NOT NULL CHECK (dimension > 0),
                    embedding BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS face_embeddings_model_dimension
                    ON face_embeddings(model_id, dimension);
                """
            )

    def enroll(
        self,
        *,
        subject_id: str,
        display_name: str,
        embedding: Iterable[float],
        model_id: str,
        consent_reference: str,
    ) -> int:
        clean_subject_id = subject_id.strip()
        clean_display_name = display_name.strip()
        clean_model_id = model_id.strip()
        clean_consent = consent_reference.strip()
        if not all(
            (clean_subject_id, clean_display_name, clean_model_id, clean_consent)
        ):
            raise ValueError(
                "subject_id, display_name, model_id, and consent_reference are required"
            )

        vector = _normalize(embedding)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO subjects (
                    subject_id, display_name, consent_reference, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(subject_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    consent_reference = excluded.consent_reference,
                    updated_at = excluded.updated_at
                """,
                (
                    clean_subject_id,
                    clean_display_name,
                    clean_consent,
                    now,
                    now,
                ),
            )
            cursor = connection.execute(
                """
                INSERT INTO face_embeddings (
                    subject_id, model_id, dimension, embedding, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    clean_subject_id,
                    clean_model_id,
                    len(vector),
                    _pack(vector),
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def match(
        self,
        embedding: Iterable[float],
        *,
        model_id: str,
        threshold: float,
        limit: int = 3,
    ) -> list[FaceMatch]:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Face-match threshold must be between 0 and 1")
        if limit < 1:
            raise ValueError("Face-match limit must be at least 1")
        clean_model_id = model_id.strip()
        if not clean_model_id:
            raise ValueError("model_id is required")

        query = _normalize(embedding)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT e.subject_id, s.display_name, e.embedding
                FROM face_embeddings AS e
                JOIN subjects AS s ON s.subject_id = e.subject_id
                WHERE e.model_id = ? AND e.dimension = ?
                """,
                (clean_model_id, len(query)),
            ).fetchall()

        best_by_subject: dict[str, FaceMatch] = {}
        for subject_id, display_name, blob in rows:
            candidate = _unpack(blob, len(query))
            similarity = max(
                -1.0,
                min(1.0, sum(left * right for left, right in zip(query, candidate))),
            )
            if similarity < threshold:
                continue
            match = FaceMatch(subject_id, display_name, similarity)
            previous = best_by_subject.get(subject_id)
            if previous is None or match.similarity > previous.similarity:
                best_by_subject[subject_id] = match

        return sorted(
            best_by_subject.values(),
            key=lambda item: item.similarity,
            reverse=True,
        )[:limit]

    def delete_subject(self, subject_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM subjects WHERE subject_id = ?", (subject_id.strip(),)
            )
            return cursor.rowcount > 0

    def list_subjects(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT subject_id, display_name, consent_reference, created_at, updated_at
                FROM subjects ORDER BY display_name, subject_id
                """
            ).fetchall()
        keys = (
            "subject_id",
            "display_name",
            "consent_reference",
            "created_at",
            "updated_at",
        )
        return [dict(zip(keys, row)) for row in rows]
