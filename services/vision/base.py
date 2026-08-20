from typing import Protocol

from schemas import RecognizedFace


class FaceRecognitionUnavailableError(RuntimeError):
    """Raised when local face recognition cannot run."""


class FaceRecognitionService(Protocol):
    """Trusted face-recognition boundary used by the HTTP application."""

    def recognize(self, image_bytes: bytes) -> list[RecognizedFace]: ...

    def enroll(
        self,
        image_bytes: bytes,
        *,
        subject_id: str,
        display_name: str,
        consent_reference: str,
    ) -> int: ...
