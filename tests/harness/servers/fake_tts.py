"""A stand-in for `services/speech` that records what it was asked to say.

This exists for exactly one assertion, and it is the strongest form I6 can
take: **"never spoken aloud" means "never sent to TTS."** The UI's speech
pipeline ends at `POST /audio/speech`; whatever arrives here is, by definition,
what the class would have heard. So instead of scraping a subtitle and hoping,
the test reads the actual text that reached the synthesiser.

It also decouples the suite from Piper: no model load, no 100-190 ms per call,
and the live `:8001` service is never touched.

Returns a real, decodable 16-bit PCM WAV so the browser's `decodeAudioData`
succeeds and the playback pipeline runs its full course (a rejected buffer
would short-circuit the very pipeline under test).
"""

from __future__ import annotations

import argparse
import struct
import time
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

SPOKEN: list[dict[str, Any]] = []


def silence_wav(seconds: float = 0.25, rate: int = 22050) -> bytes:
    frames = int(seconds * rate)
    data = b"\x00\x00" * frames
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


def create_app() -> FastAPI:
    app = FastAPI(title="fake-tts")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "voices": ["en", "vi"], "stt": False, "spoken": len(SPOKEN)}

    @app.get("/__spoken")
    async def spoken() -> dict[str, Any]:
        return {"count": len(SPOKEN), "spoken": SPOKEN}

    @app.post("/__spoken/reset")
    async def reset() -> dict[str, Any]:
        SPOKEN.clear()
        return {"ok": True}

    @app.post("/audio/speech")
    async def speech(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - a malformed body is still evidence
            body = {"_raw": (await request.body()).decode("utf-8", "replace")}
        SPOKEN.append({"ts": time.time(), "input": body.get("input"), "body": body})
        return Response(content=silence_wav(), media_type="audio/wav")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    # A long keep-alive: core's httpx client pools connections, and a server
    # that hangs up on an idle one surfaces as `ReadError` on the next health
    # probe, which reads as "the agent died" and flaps the mode mid-test.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        timeout_keep_alive=300,
    )


if __name__ == "__main__":
    main()
