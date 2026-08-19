from __future__ import annotations

from datetime import timedelta

from db import Database, fts_query, open_database, utc_now


def test_migrations_are_idempotent(tmp_path):
    path = tmp_path / "m.db"
    first = open_database(path)
    assert first.migrate() == []           # already applied by open_database
    first.close()

    second = open_database(path)           # a second process/startup
    assert second.migrate() == []
    tables = {
        row["name"]
        for row in second._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "students",
        "skills",
        "sessions",
        "observations",
        "session_summaries",
        "memories_fts",
    } <= tables
    second.close()


def test_student_and_skill_roundtrip(database: Database):
    database.upsert_student("s01", "Minh", display_name="Minh N.")
    database.update_skill("s01", "animal_vocab", 0.7, 0.5)
    database.update_skill("s01", "animal_vocab", 0.8, 0.6)   # upsert, not duplicate
    student = database.get_student("s01")
    assert student["name"] == "Minh"
    assert student["skills"] == {"animal_vocab": 0.8}
    assert database.get_student("nobody") is None


def test_skill_estimates_are_clamped(database: Database):
    database.upsert_student("s01", "Minh")
    assert database.update_skill("s01", "x", 5.0)["estimate"] == 1.0
    assert database.update_skill("s01", "x", -2.0)["estimate"] == 0.0


def test_session_lifecycle(database: Database):
    session_id = database.start_session(student_id="s01", lesson_id="en-a1-animals-01")
    assert database.get_session(session_id)["ended_at"] is None
    database.record_observation("s01", "animal_vocab", "correct", "chose cat", session_id)
    database.record_observation("s01", "animal_vocab", "wrong", "chose dog", session_id)
    assert len(database.list_observations(session_id=session_id)) == 2
    assert len(database.list_observations(student_id="s01")) == 2

    ended = database.end_session(session_id, mode="OFFLINE")
    assert ended["ended_at"] is not None
    assert ended["mode"] == "OFFLINE"


def test_recall_finds_observations(database: Database):
    session_id = database.start_session(student_id="s01")
    database.record_observation(
        "s01", "animal_vocab", "correct", "recognised the cat picture immediately", session_id
    )
    database.record_observation(
        "s01", "greetings", "wrong", "said goodbye instead of hello", session_id
    )

    hits = database.recall("cat picture", k=5)
    assert hits, "FTS5 MATCH returned nothing"
    assert "cat" in hits[0].text
    assert hits[0].when  # ISO date

    assert database.recall("submarine", k=5) == []


def test_recall_is_recency_weighted(database: Database):
    now = utc_now()
    database.record_observation(
        "s01", "animal_vocab", "wrong", "confused the bird and the fish", ts=now - timedelta(days=200)
    )
    database.record_observation(
        "s01", "animal_vocab", "correct", "named the bird correctly", ts=now
    )
    hits = database.recall("bird", k=5)
    assert len(hits) == 2
    assert "named the bird correctly" in hits[0].text, "the newer memory should rank first"


def test_recall_respects_k_and_student_filter(database: Database):
    for i in range(6):
        database.record_observation("s01", "animal_vocab", "correct", f"named the cat number {i}")
    database.record_observation("s02", "animal_vocab", "correct", "another cat entirely")

    assert len(database.recall("cat", k=3)) == 3
    assert len(database.recall("cat", k=99)) == 7
    only_s01 = database.recall("cat", k=99, student_id="s01")
    assert len(only_s01) == 6


def test_recall_does_not_match_on_unindexed_metadata(database: Database):
    database.record_observation("s17", "animal_vocab", "correct", "named the dog")
    assert database.recall("s17") == []       # student_id column is UNINDEXED
    assert database.recall("named the dog")


def test_recall_tolerates_hostile_input(database: Database):
    database.record_observation("s01", "animal_vocab", "correct", "named the dog")
    for query in ['"', "AND OR NOT", "* * *", "", "   ", "dog OR (", 'dog" OR "']:
        database.recall(query)      # must not raise
    assert fts_query("!!!") == ""


def test_session_summary_is_recallable_and_upsertable(database: Database):
    session_id = database.start_session(student_id="s01")
    database.write_session_summary(
        session_id, "Minh mixed up bird and fish today.", ["animal_vocab"], ["listening_a1"]
    )
    database.write_session_summary(
        session_id, "Minh confidently named every animal.", [], ["roleplay"]
    )
    stored = database.get_session_summary(session_id)
    assert stored["summary"] == "Minh confidently named every animal."
    assert stored["nextFocus"] == ["roleplay"]

    hits = database.recall("confidently named", k=5)
    assert hits and hits[0].text == "Minh confidently named every animal."
    # the superseded summary is gone from the index, not duplicated
    assert database.recall("mixed up bird") == []


def test_fts_query_quotes_tokens():
    assert fts_query("cat dog") == '"cat" OR "dog"'
    assert fts_query('cat" OR sqlite_master') == '"cat" OR "OR" OR "sqlite_master"'


def test_observation_mode_is_optional_and_migrated(tmp_path):
    path = tmp_path / "mode.db"
    database = open_database(path)
    columns = {
        row["name"]
        for row in database._conn.execute("PRAGMA table_info(observations)")
    }
    assert "mode" in columns
    session_id = database.start_session(student_id="s01")
    database.record_observation("s01", "animal_vocab", "correct", "unit=demo; outcome=correct", session_id)
    database.record_observation(
        "s01",
        "animal_vocab",
        "correct",
        "unit=demo; outcome=correct; mode=point",
        session_id,
        mode="point",
    )
    rows = database.list_observations(student_id="s01")
    assert rows[0]["mode"] is None
    assert rows[1]["mode"] == "point"
    database.close()
    again = open_database(path)
    assert again.migrate() == []
    assert again.list_observations(student_id="s01")[1]["mode"] == "point"
    again.close()


def test_only_a_recently_interrupted_period_is_resumable(tmp_path) -> None:
    """Yesterday's unclosed lesson is abandoned, not interrupted.

    The live database holds dozens of sessions nobody ever closed. Resuming the
    newest of those on a morning boot would drop a class into the middle of a
    lesson from days ago, which is worse than starting fresh. The age bound is
    what separates "the power went out five minutes ago" from "this row was
    left behind".
    """
    import datetime as dt

    from db import open_database

    database = open_database(tmp_path / "bright.db")
    fresh = database.start_session(student_id="learner-1", lesson_id="gs3-u1-hello")

    found = database.find_open_session()
    assert found is not None and found["id"] == fresh

    # Same row, but the window is now narrower than its age.
    assert database.find_open_session(within_s=0.0) is None

    # An old unclosed row is never offered, however many there are.
    stale = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)
    database.start_session(student_id="learner-1", lesson_id="gs3-u1-hello", session_id="old")
    with database._lock:  # noqa: SLF001 -- the test is about what the query returns
        database._conn.execute(
            "UPDATE sessions SET started_at = ? WHERE id = 'old'", (stale.isoformat(),)
        )
    again = database.find_open_session()
    assert again is not None and again["id"] == fresh, "the old row must never win"
