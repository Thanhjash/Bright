from __future__ import annotations

import hashlib
import threading
import os
from pathlib import Path

MODELS = Path(os.environ.get("VISION_MODELS", Path(__file__).resolve().parents[2] / "models" / "vision"))
DETECTOR = MODELS / "face_detection_yunet_2023mar.onnx"
RECOGNIZER = MODELS / "face_recognition_sface_2021dec.onnx"
# SFace cosine similarity. 0.363 is OpenCV's own published operating point for
# this checkpoint; raising it trades recall for precision, and NORTH-STAR is
# explicit about which way to err: "Losing a data point is cheap. Attributing a
# child's failure to a different child is not."
COSINE_THRESHOLD = float(os.environ.get("FACE_COSINE_THRESHOLD", "0.363"))
from typing import Any

from base import FaceRecognitionUnavailableError
from store import FaceEmbeddingStore
from schemas import BoundingBox, RecognizedFace


class OpenCVFaceRecognition:
    """CPU-only YuNet detection plus SFace embedding and cosine matching."""

    def __init__(
        self,
        detector_path: Path | None = None,
        recognizer_path: Path | None = None,
        *,
        store: FaceEmbeddingStore | None = None,
        cosine_threshold: float | None = None,
    ):
        detector_path = detector_path or DETECTOR
        recognizer_path = recognizer_path or RECOGNIZER
        cosine_threshold = COSINE_THRESHOLD if cosine_threshold is None else cosine_threshold
        if not 0.0 <= cosine_threshold <= 1.0:
            raise ValueError("Face cosine threshold must be between 0 and 1")
        self.detector_path = Path(detector_path)
        self.recognizer_path = Path(recognizer_path)
        self.cosine_threshold = cosine_threshold
        self._store = store
        self._cv: Any | None = None
        self._np: Any | None = None
        self._detector: Any | None = None
        self._recognizer: Any | None = None
        self._model_id: str | None = None
        self._lock = threading.Lock()

    @property
    def store(self) -> FaceEmbeddingStore:
        if self._store is None:
            self._store = FaceEmbeddingStore()
        return self._store

    @property
    def model_id(self) -> str:
        self._load_models()
        assert self._model_id is not None
        return self._model_id

    def _load_models(self) -> None:
        if self._detector is not None:
            return
        for name, path in (
            ("YuNet detector", self.detector_path),
            ("SFace recognizer", self.recognizer_path),
        ):
            if not path.is_file():
                raise FaceRecognitionUnavailableError(
                    f"{name} model not found: {path}. "
                    "Run: ./tools/fetch-face-models.py"
                )
        try:
            import cv2 as cv
            import numpy as np
        except ImportError as error:
            raise FaceRecognitionUnavailableError(
                "OpenCV is not installed in the vision venv."
            ) from error

        try:
            detector = cv.FaceDetectorYN.create(
                str(self.detector_path), "", (320, 320), 0.9, 0.3, 5000
            )
            recognizer = cv.FaceRecognizerSF.create(str(self.recognizer_path), "")
        except Exception as error:
            raise FaceRecognitionUnavailableError(
                f"Could not load YuNet/SFace models: {error}"
            ) from error

        digest = hashlib.sha256(self.recognizer_path.read_bytes()).hexdigest()[:16]
        self._cv = cv
        self._np = np
        self._detector = detector
        self._recognizer = recognizer
        self._model_id = f"opencv-sface:{digest}"

    def _decode_image(self, image_bytes: bytes) -> Any:
        if not image_bytes:
            raise ValueError("Image cannot be empty")
        self._load_models()
        assert self._cv is not None and self._np is not None
        encoded = self._np.frombuffer(image_bytes, dtype=self._np.uint8)
        image = self._cv.imdecode(encoded, self._cv.IMREAD_COLOR)
        if image is None:
            raise ValueError("Image must be a valid PNG, JPEG, or WebP file")
        return image

    @staticmethod
    def _bounds(face: Any, width: int, height: int) -> BoundingBox | None:
        x, y, box_width, box_height = (float(value) for value in face[:4])
        x_min = max(0.0, min(1.0, x / width))
        y_min = max(0.0, min(1.0, y / height))
        x_max = max(0.0, min(1.0, (x + box_width) / width))
        y_max = max(0.0, min(1.0, (y + box_height) / height))
        if x_min >= x_max or y_min >= y_max:
            return None
        return BoundingBox(
            x_min=x_min,
            y_min=y_min,
            x_max=x_max,
            y_max=y_max,
        )

    def _extract(self, image_bytes: bytes) -> list[tuple[BoundingBox, float, list[float]]]:
        image = self._decode_image(image_bytes)
        assert self._detector is not None and self._recognizer is not None
        height, width = image.shape[:2]
        self._detector.setInputSize((width, height))
        _, faces = self._detector.detect(image)
        if faces is None:
            return []

        extracted = []
        for face in faces:
            bounds = self._bounds(face, width, height)
            if bounds is None:
                continue
            aligned = self._recognizer.alignCrop(image, face[:-1])
            feature = self._recognizer.feature(aligned)
            vector = [float(value) for value in feature.reshape(-1)]
            extracted.append((bounds, float(face[14]), vector))
        return extracted

    def recognize(self, image_bytes: bytes) -> list[RecognizedFace]:
        with self._lock:
            extracted = self._extract(image_bytes)

        results = []
        for bounds, detection_score, embedding in extracted:
            matches = self.store.match(
                embedding,
                model_id=self.model_id,
                threshold=self.cosine_threshold,
                limit=1,
            )
            match = matches[0] if matches else None
            results.append(
                RecognizedFace(
                    bounds=bounds,
                    detection_score=detection_score,
                    subject_id=match.subject_id if match else None,
                    display_name=match.display_name if match else None,
                    similarity=match.similarity if match else None,
                )
            )
        return results

    def enroll(
        self,
        image_bytes: bytes,
        *,
        subject_id: str,
        display_name: str,
        consent_reference: str,
    ) -> int:
        with self._lock:
            extracted = self._extract(image_bytes)
        if len(extracted) != 1:
            raise ValueError(
                "Enrollment image must contain exactly one clearly detected face"
            )
        _, _, embedding = extracted[0]
        return self.store.enroll(
            subject_id=subject_id,
            display_name=display_name,
            embedding=embedding,
            model_id=self.model_id,
            consent_reference=consent_reference,
        )
