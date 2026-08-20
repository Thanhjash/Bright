"""The three perception rules, asserted rather than described.

NORTH-STAR, "Identity is the system's job, not the model's", binds these from
the first line of perception code. Detection itself is upstream OpenCV; what is
ours -- and what these cover -- is the store, the confidence rule, and what the
rest of Bright is allowed to learn from a camera.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import FaceEnrollmentRequest  # noqa: E402
from store import FaceEmbeddingStore  # noqa: E402

MODEL = "opencv-sface:testhash"


def store(tmp_path: Path) -> FaceEmbeddingStore:
    return FaceEmbeddingStore(tmp_path / "faces.db")


def face(seed: float, dim: int = 128) -> list[float]:
    """A deterministic unit-ish vector. Cosine, so magnitude does not matter."""
    return [seed + i * 0.01 for i in range(dim)]


def test_a_known_child_is_matched_and_named(tmp_path: Path) -> None:
    s = store(tmp_path)
    s.enroll(subject_id="learner-1", display_name="Minh", embedding=face(1.0),
             model_id=MODEL, consent_reference="consent-2026-03-form-14")
    hits = s.match(face(1.0), model_id=MODEL, threshold=0.9)
    assert [h.subject_id for h in hits] == ["learner-1"]
    assert hits[0].display_name == "Minh"
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-6)


def test_a_stranger_is_nobody_rather_than_the_closest_child(tmp_path: Path) -> None:
    """Rule 1. The expensive mistake is confident misattribution, not a miss.

    "Losing a data point is cheap. Attributing a child's failure to a different
    child is not." A stranger in front of the camera must come back empty, so
    Core opens nobody's memory.
    """
    s = store(tmp_path)
    s.enroll(subject_id="learner-1", display_name="Minh", embedding=face(1.0),
             model_id=MODEL, consent_reference="c1")
    # Orthogonal-ish: alternating sign kills the cosine against a monotone vector.
    stranger = [(-1.0) ** i * (1.0 + i * 0.01) for i in range(128)]
    assert s.match(stranger, model_id=MODEL, threshold=0.363) == []


def test_embeddings_never_cross_a_model_version(tmp_path: Path) -> None:
    """`model_id` carries a hash of the recogniser weights.

    Matching a vector produced by one checkpoint against another's is not a
    worse match, it is a meaningless number -- so the store scopes the query by
    model_id and a swapped model simply finds nobody.
    """
    s = store(tmp_path)
    s.enroll(subject_id="learner-1", display_name="Minh", embedding=face(1.0),
             model_id=MODEL, consent_reference="c1")
    assert s.match(face(1.0), model_id="opencv-sface:otherhash", threshold=0.9) == []


def test_forgetting_a_child_takes_the_biometrics_with_them(tmp_path: Path) -> None:
    """Rule 2. An embedding is not anonymisation; it is student data.

    ON DELETE CASCADE is the whole point: erasure has to reach the templates,
    or "we deleted their record" is a false statement.
    """
    s = store(tmp_path)
    s.enroll(subject_id="learner-1", display_name="Minh", embedding=face(1.0),
             model_id=MODEL, consent_reference="c1")
    assert s.match(face(1.0), model_id=MODEL, threshold=0.9)
    assert s.delete_subject("learner-1") is True
    assert s.match(face(1.0), model_id=MODEL, threshold=0.9) == []
    assert s.list_subjects() == []
    assert s.delete_subject("learner-1") is False


def test_enrolment_cannot_be_written_without_consent() -> None:
    """Rule 3. Consent is in the TYPE, so a caller cannot forget it.

    `consent_confirmed: Literal[True]` means False and absent are both invalid,
    and `consent_reference` names the paper that was signed.
    """
    ok = FaceEnrollmentRequest(
        image_base64="Zm9v", subject_id="learner-1", display_name="Minh",
        consent_confirmed=True, consent_reference="consent-2026-03-form-14")
    assert ok.consent_reference

    with pytest.raises(Exception):
        FaceEnrollmentRequest(
            image_base64="Zm9v", subject_id="learner-1", display_name="Minh",
            consent_confirmed=False, consent_reference="c")  # type: ignore[arg-type]
    with pytest.raises(Exception):
        FaceEnrollmentRequest(
            image_base64="Zm9v", subject_id="learner-1", display_name="Minh",
            consent_confirmed=True, consent_reference="")


def test_the_store_holds_no_image(tmp_path: Path) -> None:
    """Rule 2, the other half: raw video is not stored by default.

    Asserted against the schema rather than by inspection, so a column added
    later that could hold a photograph fails here first.
    """
    s = store(tmp_path)
    s.enroll(subject_id="learner-1", display_name="Minh", embedding=face(1.0),
             model_id=MODEL, consent_reference="c1")
    with s._connect() as c:  # noqa: SLF001 -- this test is about the schema
        columns = {
            table: {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            for table in ("subjects", "face_embeddings")
        }
    assert columns["face_embeddings"] == {
        "embedding_id", "subject_id", "model_id", "dimension", "embedding", "created_at"}
    for table, names in columns.items():
        assert not {n for n in names if "image" in n or "photo" in n or "frame" in n}, table
