"""Bright vision service — who is in front of the camera, and how sure are we.

Perception answers exactly one question (NORTH-STAR, "Identity is the system's
job, not the model's"):

    Which existing student_id is this -- and how sure are we?

It does NOT answer what the child knows. The teacher receives an id and,
through it, that learner's recorded evidence. **She never receives a face, an
image, an embedding, or a name she is expected to match to a person.** Nothing
in this service is reachable from her tool surface, and that is deliberate.

The recognizer, the embedding store and the schemas are ported from the owner's
own ClassroomAI project (`references/ClassroomAI_ai-core/classroom_ai/vision/`),
which already had the hard parts right: CPU-only YuNet detection + SFace
embeddings, consent in the type rather than in a policy document, and a store
that keeps templates and never photographs.

THE THREE BINDING RULES, and where each one lives:

1. **Uncertain identity means no student-memory write.** `recognize` returns
   `subject_id: null` below the cosine threshold rather than a best guess, and
   says so in `confident`. Core must not open a learner's memory on an
   unconfident row. Losing a data point is cheap; attributing one child's
   failure to another is not.
2. **Raw video is not stored by default.** Frames are decoded, measured and
   dropped inside one request. The store holds normalized embeddings, and
   `DELETE FROM subjects` cascades to them -- erasing a child erases their
   biometrics, because an embedding is not anonymisation.
3. **Identity is bound before class, not inferred during it.** `/vision/enroll`
   demands `consent_confirmed: true` and a `consent_reference` naming the paper
   that was signed, and it refuses an image with more than one face. The camera
   then matches; it never enrols silently.

Enrolment belongs to the adult console, never the projector.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))

from base import FaceRecognitionUnavailableError  # noqa: E402
from recognizer import COSINE_THRESHOLD, OpenCVFaceRecognition  # noqa: E402
from schemas import FaceEnrollmentRequest, FaceEnrollmentResult, RecognizedFace  # noqa: E402
from store import FaceEmbeddingStore  # noqa: E402

log = logging.getLogger("vision")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

HOST = os.environ.get("VISION_HOST", "127.0.0.1")
# Reserved for vision since the first topology drawing: "localhost:8002 vision
# — face, hand, tracking" (docs/design/runtime-topology.md).
PORT = int(os.environ.get("VISION_PORT", "8002"))
MAX_IMAGE_BYTES = int(os.environ.get("VISION_MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))

_state: dict[str, Any] = {"engine": None, "error": None}

app = FastAPI(title="bright-vision")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get(
        "VISION_CORS", "http://127.0.0.1:3000,http://localhost:3000"
    ).split(",") if o],
    allow_methods=["*"],
    allow_headers=["*"],
)


def engine() -> OpenCVFaceRecognition:
    """Built once, lazily. A missing model must not stop the room from booting.

    The classroom runs without a camera; a school that has not enrolled anyone
    simply never calls this. Failing at boot would take the lesson down with it.
    """
    if _state["engine"] is None:
        try:
            _state["engine"] = OpenCVFaceRecognition(store=FaceEmbeddingStore())
            _state["error"] = None
        except FaceRecognitionUnavailableError as exc:
            _state["error"] = str(exc)
            raise HTTPException(503, str(exc)) from exc
    return _state["engine"]


class RecognizeRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=15_000_000)


class SeenFace(BaseModel):
    """One face, and the only two things the rest of Bright is allowed to want."""

    subject_id: str | None
    display_name: str | None
    similarity: float | None
    detection_score: float
    # The whole point of rule 1, computed here so no caller has to remember the
    # threshold or get the comparison the wrong way round.
    confident: bool


class RecognizeResult(BaseModel):
    faces: list[SeenFace]
    threshold: float
    model_id: str


def _decode(image_base64: str) -> bytes:
    import base64
    import binascii

    try:
        raw = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, "image_base64 is not valid base64") from exc
    if not raw:
        raise HTTPException(400, "image is empty")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"image over {MAX_IMAGE_BYTES} bytes")
    return raw


def _seen(face: RecognizedFace) -> SeenFace:
    similarity = face.similarity
    return SeenFace(
        subject_id=face.subject_id,
        display_name=face.display_name,
        similarity=similarity,
        detection_score=face.detection_score,
        confident=bool(face.subject_id) and similarity is not None
        and similarity >= COSINE_THRESHOLD,
    )


@app.get("/health")
def health() -> dict[str, Any]:
    ready, error = _state["engine"] is not None, _state["error"]
    if not ready and error is None:
        try:
            engine()
            ready = True
        except HTTPException as exc:
            error = str(exc.detail)
    return {
        "status": "ok" if ready else "degraded",
        "faceRecognition": ready,
        "error": error,
        "threshold": COSINE_THRESHOLD,
        "enrolled": len(FaceEmbeddingStore().list_subjects()),
    }


@app.post("/vision/recognize", response_model=RecognizeResult)
def recognize(req: RecognizeRequest) -> RecognizeResult:
    """Match a frame against enrolled templates. Never enrols, never stores it."""
    eng = engine()
    try:
        faces = eng.recognize(_decode(req.image_base64))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RecognizeResult(
        faces=[_seen(f) for f in faces],
        threshold=COSINE_THRESHOLD,
        model_id=eng.model_id,
    )


@app.post("/vision/enroll", response_model=FaceEnrollmentResult)
def enroll(req: FaceEnrollmentRequest) -> FaceEnrollmentResult:
    """Bind a face to a student_id. Deliberate, consented, adult-console only.

    `consent_confirmed: Literal[True]` and a non-empty `consent_reference` are
    in the request TYPE, so a caller cannot omit them and a reviewer cannot
    miss them. The reference should name the signed paper, not repeat the
    child's name.
    """
    eng = engine()
    try:
        embedding_id = eng.enroll(
            _decode(req.image_base64),
            subject_id=req.subject_id,
            display_name=req.display_name,
            consent_reference=req.consent_reference,
        )
    except ValueError as exc:
        # "exactly one clearly detected face" -- a class photo is not consent.
        raise HTTPException(400, str(exc)) from exc
    log.info("enrolled subject=%s embedding=%s", req.subject_id, embedding_id)
    return FaceEnrollmentResult(
        embedding_id=embedding_id,
        subject_id=req.subject_id,
        display_name=req.display_name,
    )


@app.get("/vision/subjects")
def subjects() -> dict[str, Any]:
    """Who is enrolled, for the adult. Never for the projector."""
    return {"subjects": FaceEmbeddingStore().list_subjects()}


@app.delete("/vision/subjects/{subject_id}")
def forget(subject_id: str) -> dict[str, Any]:
    """Erase a child's biometrics. Rule 2: templates are student data.

    `ON DELETE CASCADE` takes the embeddings with the subject, so this is a
    real erasure and not a hidden orphan.
    """
    return {"deleted": FaceEmbeddingStore().delete_subject(subject_id)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
