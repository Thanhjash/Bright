"""Who is sitting in front of the camera — Core's thin view of :8002.

Core asks one question and accepts one kind of answer:

    Which existing student_id is this -- and how sure are we?

It never sees a face, an image or an embedding. Those live in the vision
service and stop there; what crosses this boundary is an id and a number.
The teacher does not even get that: she gets an id and, through it, that
learner's recorded evidence (NORTH-STAR, "Identity is the system's job").

THE RULE THIS FILE EXISTS TO ENFORCE, and the only one that is subtle:

> **Uncertain identity means no student-memory write.** An observation with no
> confident subject is a classroom event, not a fact about a child. Losing a
> data point is cheap. Attributing a child's failure to a different child is
> not.

So `identify` returns None for anything short of one confidently-matched face,
and None means the room falls back to the deployment's declared learner rather
than guessing. Two faces in frame is also None: a child sitting beside a
classmate must not become that classmate.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger("bright.perception")

VISION_URL = os.environ.get("VISION_URL", "http://127.0.0.1:8002").rstrip("/")
# Long enough for a CPU detector on a cheap box, short enough that a dead
# vision service cannot hold up the start of a lesson.
TIMEOUT_S = float(os.environ.get("VISION_TIMEOUT_S", "8"))
# How long a resolved identity stays good. A child does not become another
# child mid-period, but a stale answer from this morning must not open a
# session for someone who went home.
IDENTITY_TTL_S = float(os.environ.get("VISION_IDENTITY_TTL_S", "900"))


@dataclass(frozen=True)
class Identified:
    """A confident match, and nothing else. No bounds, no embedding, no image."""

    student_id: str
    display_name: str
    similarity: float
    at: float

    def fresh(self, *, now: float | None = None) -> bool:
        return (now or time.time()) - self.at <= IDENTITY_TTL_S


def vision_up() -> bool:
    try:
        with urllib.request.urlopen(VISION_URL + "/health", timeout=2) as response:
            return json.loads(response.read()).get("faceRecognition") is True
    except Exception:  # noqa: BLE001 -- a camera is optional; the room is not
        return False


def identify(image_bytes: bytes) -> Identified | None:
    """One frame in, at most one confident child out.

    Returns None -- deliberately, not as an error -- when the service is down,
    when nobody is recognised, when the match is below threshold, and when more
    than one face is confidently matched. Every one of those means "we do not
    know", and the caller must treat them identically.
    """
    if not image_bytes:
        return None
    payload = json.dumps({"image_base64": base64.b64encode(image_bytes).decode()}).encode()
    request = urllib.request.Request(
        VISION_URL + "/vision/recognize",
        data=payload,
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        log.warning("vision refused a frame (%s)", exc.code)
        return None
    except Exception as exc:  # noqa: BLE001 -- never let perception stop teaching
        log.warning("vision unreachable (%s)", exc)
        return None

    confident = [
        face for face in body.get("faces", [])
        if face.get("confident") and face.get("subject_id")
    ]
    if len(confident) != 1:
        # Zero: a stranger, or an empty chair. More than one: a child beside a
        # classmate, and picking the higher score would be exactly the
        # misattribution the rule forbids.
        if len(confident) > 1:
            log.info("perception saw %d confident faces; attributing to none", len(confident))
        return None

    face = confident[0]
    return Identified(
        student_id=str(face["subject_id"]),
        display_name=str(face.get("display_name") or face["subject_id"]),
        similarity=float(face.get("similarity") or 0.0),
        at=time.time(),
    )
