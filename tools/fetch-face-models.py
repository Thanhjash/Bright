#!/usr/bin/env python3
"""Fetch the CPU face models for services/vision: YuNet + SFace.

Both come from OpenCV's own model zoo, pinned to a release tag and verified by
checksum -- a face model that silently changed would invalidate every embedding
already enrolled, because `model_id` carries the recognizer's hash and matching
is scoped to it.

Checksums and URLs are the owner's, from
references/ClassroomAI_ai-core/scripts/download_face_models.py.
"""
from __future__ import annotations
import hashlib, shutil, sys, tempfile, urllib.request
from pathlib import Path

MODELS = Path(__file__).resolve().parents[1] / "models" / "vision"
ZOO = "https://github.com/opencv/opencv_zoo/raw/4.10.0/models"
WANT = {
    "face_detection_yunet_2023mar.onnx": (
        f"{ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": (
        f"{ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}

def sha256(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            d.update(chunk)
    return d.hexdigest()

def main() -> int:
    MODELS.mkdir(parents=True, exist_ok=True)
    for name, (url, want) in WANT.items():
        target = MODELS / name
        if target.exists():
            if sha256(target) == want:
                print(f"ok      {name}")
                continue
            print(f"CHECKSUM MISMATCH: {target} — inspect it, then delete to refetch", file=sys.stderr)
            return 2
        print(f"fetch   {name}")
        with urllib.request.urlopen(url, timeout=300) as r, \
             tempfile.NamedTemporaryFile(dir=MODELS, delete=False) as tmp:
            shutil.copyfileobj(r, tmp)
            part = Path(tmp.name)
        got = sha256(part)
        if got != want:
            part.unlink(missing_ok=True)
            print(f"BAD CHECKSUM for {name}: {got}", file=sys.stderr)
            return 2
        part.replace(target)
        print(f"ok      {name}")
    print(f"\n-> {MODELS}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
