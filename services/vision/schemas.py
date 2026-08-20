from typing import Literal

from pydantic import BaseModel, Field, model_validator


class BoundingBox(BaseModel):
    """Normalized image bounds in the inclusive 0..1 coordinate space."""

    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_order(self) -> "BoundingBox":
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("bounding-box minimums must be smaller than maximums")
        return self


class RecognizedFace(BaseModel):
    bounds: BoundingBox
    detection_score: float = Field(ge=0.0, le=1.0)
    subject_id: str | None = None
    display_name: str | None = None
    similarity: float | None = Field(default=None, ge=-1.0, le=1.0)


class FaceEnrollmentRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=15_000_000)
    subject_id: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    display_name: str = Field(min_length=1, max_length=100)
    consent_confirmed: Literal[True]
    consent_reference: str = Field(min_length=1, max_length=200)


class FaceEnrollmentResult(BaseModel):
    embedding_id: int
    subject_id: str
    display_name: str
