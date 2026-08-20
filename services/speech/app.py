"""Bright speech service — TTS (Piper) + STT (faster-whisper).

OpenAI-compatible surface so any frontend can talk to it unchanged:
    POST /audio/speech            -> WAV bytes
    POST /audio/transcriptions    -> {"text": ...}

THE ONE RULE THAT MATTERS: models are loaded ONCE at startup and never
reloaded. Published Piper benchmarks report ~1500ms first-audio; that number
is cold start. Measured here on 2026-08-11:

    model load        1.52 s   <- paid once, at startup
    21-char sentence  100 ms
    76-char sentence  323 ms
    throughput        0.07x realtime

Reload the model per request and you turn a 100 ms service into a 1.6 s one.
(POST /admin/model swaps the STT model deliberately and rarely — an operator
action between lessons, not something on the request path.)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from asr import AsrProvider, FasterWhisperProvider, parse_languages

log = logging.getLogger("speech")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

ROOT = Path(__file__).resolve().parents[2]
PIPER_DIR = Path(os.environ.get("PIPER_DIR", ROOT / "models" / "piper"))
WHISPER_DIR = Path(os.environ.get("WHISPER_DIR", ROOT / "models" / "whisper"))
# STT model choice — measured on this hardware 2026-08-11 (12 CPU threads, int8).
# Whisper always processes a 30 s window, so cost is per CALL, not per second of
# audio. Numbers below are seconds per call, and accuracy on 3 clean English
# sentences:
#
#     tiny.en           0.66 s   3/3
#     base.en           1.80 s   2/3
#     small.en          3.35 s   3/3
#     large-v3-turbo   11.53 s   3/3     <- 17x slower than tiny for no gain
#
# CAVEAT: those samples are Piper-generated, clean, and noise-free. They cannot
# separate these models. Real children in a real room will degrade tiny far
# faster than small. Do not read the table as "tiny is enough" — read it as
# "large-v3-turbo is definitively wrong here" (SP-7 needs real child audio).
#
# Mitigation that makes this choice less critical: most classroom utterances
# answer a KNOWN prompt, so core matches against an expected-answer set rather
# than trusting open transcription.
#
# The resident model is now swappable at runtime via POST /admin/model, so this
# is the *startup* default, not a restart-locked decision. See tests/room/.
#
# LANGUAGE — measured on the running :8001 service, 2026-08-18, load avg 13.8
# (absolute times inflated by contention; read them as relative, not literal):
#
#   1.7s Vietnamese clip, auto language-ID   -> detected es (Spanish) p=0.57
#                                                "Sin chao, costa un contei la min!"
#   same clip, language=vi forced            -> "Xin chào cô Tahu, con Tây là mình."
#   1.4s English clip, auto language-ID      -> detected en p=0.94 (correct)
#   same clip, language=en forced            -> same text, ~35% faster (no detect pass)
#
# Whisper's own language-ID argmax is unreliable on the length of utterance a
# classroom actually produces — a 1.7s Vietnamese greeting lost to Spanish
# outright. DO NOT trust bare auto-detect. The fix (asr.py FasterWhisperProvider):
# when no language is forced, detect once and CLAMP to whichever language in
# the deployment's allowed set (ASR_LANGUAGES below) scored highest, instead of
# trusting the raw global argmax. Confirmed on this build: for the same clips,
# clamping to {en, vi} recovers vi/en correctly even when the unclamped top-1
# guess is wrong. Falls back to the first allowed language if detection itself
# is unavailable or errors — a degraded transcript beats a 500 in a classroom.
#
# CAVEAT (repeated for a second reason): these are Piper synthetic clips, not
# a child speaking. They confirm the clamp mechanism works; they do not
# validate accuracy on real classroom Vietnamese/English code-switching.
# THE DEFAULT MUST NOT BE AN `.en` CHECKPOINT. Everything above this line --
# the clamp, the allowed set, the Spanish incident -- is machinery for choosing
# between two languages, and this default was `small.en` for two days: weights
# containing exactly one. `.en` has no Vietnamese in it, so forcing
# `language=vi` on it cannot produce Vietnamese at all. It was masked because
# scripts/teacher-agent-l1.sh exports WHISPER_MODEL=base and every dev run went
# through the launcher -- but infra/systemd/bright.env.example, the appliance
# that ships, carried the same `.en` value and had nobody to mask it.
#
# WHY `base` AND NOT `small` -- measured on the running :8001 service
# 2026-08-20, Piper `vi` clips, ASR_LANGUAGES=en,vi, three repeats each:
#
#   "Con không biết"              base  'Bà không biết'                 2.5s
#                                 small ''  <- EMPTY, 3/3, every time   6.3s
#   "Con chưa hiểu bài này cô ạ"  base  'phóng chứ hiểu bài này của ạ'  2.5s
#                                 small 'phong chứ hiểu bài này của ạ'  7.0s
#   "Chào cô, con tên là Minh"    base  'Chào cố con tay là mình'       2.5s
#                                 small 'Chào cổ, con tên là mình'      8.1s
#
# `small` is better on the long clip and 3x slower, and it returns NOTHING on
# the short one -- and "Con không biết" is the sentence a stuck child says, the
# single utterance this system most needs to hear. An empty transcript is not a
# worse answer, it is silence: the room cannot tell it from a child who never
# spoke. So `base` is the floor, for the same reason the launcher already gives
# for preferring it over `tiny`.
#
# Neither is good, and neither has been tested on a real child (these are
# synthetic Piper clips -- the caveat above applies here too). This is the best
# available choice, not a solved problem.
#
# All three declarations now agree: here, teacher-agent-l1.sh:190, and
# infra/systemd/bright.env.example. A guard in tests/ asserts the shape of the
# rule rather than the model name, checking the two settings against each
# other: if ASR_LANGUAGES declares more than one language, the resident weights
# may not be monolingual. An English-only appliance declares ASR_LANGUAGES=en
# and is then free to run `.en` -- what the guard refuses is a deployment
# claiming two languages while shipping one.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")
WHISPER_THREADS = int(os.environ.get("WHISPER_THREADS", "0")) or (os.cpu_count() or 4)
HOST = os.environ.get("SPEECH_HOST", "127.0.0.1")
PORT = int(os.environ.get("SPEECH_PORT", "8001"))
MAX_ASR_UPLOAD_BYTES = int(os.environ.get("ASR_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
# NS-7: the deployment declares itself; this service never names a language.
# ASR_LANGUAGES is the deployment-declared allowed set for auto language-ID
# (defaults to en,vi — this appliance's current two languages). classroom-core
# reads the real home/school/target languages from content/library/index.md
# and can override per-request via the `languages` form field below; the
# speech service has no business reading the library itself.
ASR_LANGUAGES = os.environ.get("ASR_LANGUAGES", "en,vi")

# voice id -> piper onnx filename
VOICES: dict[str, str] = {
    "en": "en_US-lessac-medium.onnx",
    "vi": "vi_VN-vais1000-medium.onnx",
}
DEFAULT_VOICE = "en"
# The voice for text carrying the marked script (`_VI_LETTER` below). It is a
# deployment fact, like ASR_LANGUAGES: a school running one language sets it to
# that voice, or to a voice id it has not installed, and segmentation stops
# having anything to choose.
MARKED_VOICE = os.environ.get("TTS_MARKED_VOICE", "vi")
# piper | vieneu. VieNeu keeps Vietnamese tones through a code-switch and Piper
# does not; Piper is 15-20x faster. See services/speech/tts_vieneu.py for the
# measurement and why a cache is what makes the slow one usable.
TTS_ENGINE = os.environ.get("TTS_ENGINE", "piper").strip().lower()
_vieneu: Any = None


def vieneu():
    """Built on first use, never at boot: the room must come up without it."""
    global _vieneu
    if _vieneu is None:
        from tts_vieneu import VieNeuProvider
        _vieneu = VieNeuProvider()
    return _vieneu

_state: dict[str, Any] = {
    "voices": {},
    "whisper": None,
    "asr": None,
    "whisper_error": None,
    "whisper_model": WHISPER_MODEL,
}
# Piper's ONNX session is not safe to call concurrently from threads.
_tts_lock = asyncio.Lock()
# Serialises model swaps only. Transcription is NOT held under it: the running
# model is read once into a local before inference, so a swap mid-request just
# means that request finishes on the old model.
_swap_lock = asyncio.Lock()
_asr_lock = asyncio.Lock()

# faster-whisper resolves these names against its own repo map; local_files_only
# means the snapshot must already be in WHISPER_DIR. Anything not listed here is
# refused rather than triggering a download attempt at demo time.
KNOWN_MODELS: dict[str, str] = {
    "tiny.en": "models--Systran--faster-whisper-tiny.en",
    "tiny": "models--Systran--faster-whisper-tiny",
    "base.en": "models--Systran--faster-whisper-base.en",
    "base": "models--Systran--faster-whisper-base",
    "small.en": "models--Systran--faster-whisper-small.en",
    "small": "models--Systran--faster-whisper-small",
    "large-v3-turbo": "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo",
}


def _available_models() -> list[str]:
    return sorted(n for n, d in KNOWN_MODELS.items() if (WHISPER_DIR / d).is_dir())


def _load_voices() -> None:
    from piper import PiperVoice

    for vid, fname in VOICES.items():
        path = PIPER_DIR / fname
        if not path.exists():
            log.warning("voice %s missing at %s — skipping", vid, path)
            continue
        t = time.perf_counter()
        _state["voices"][vid] = PiperVoice.load(str(path))
        log.info("loaded voice %s in %.2fs", vid, time.perf_counter() - t)
    if not _state["voices"]:
        log.error("NO VOICES LOADED. Run scripts/fetch-models.sh")


def _build_whisper(name: str) -> tuple[AsrProvider, float]:
    """Construct a WhisperModel. Raises on failure; caller decides what that means."""
    from faster_whisper import WhisperModel

    t = time.perf_counter()
    model = WhisperModel(
        name,
        device="cpu",
        compute_type=WHISPER_COMPUTE,
        download_root=str(WHISPER_DIR),
        local_files_only=True,
        cpu_threads=WHISPER_THREADS,
    )
    return FasterWhisperProvider(model, name), time.perf_counter() - t


def _load_whisper() -> None:
    try:
        provider, dt = _build_whisper(WHISPER_MODEL)
        _state["asr"] = provider
        _state["whisper"] = provider  # compatibility for existing health/tests
        _state["whisper_model"] = WHISPER_MODEL
        log.info("loaded whisper %s in %.2fs", WHISPER_MODEL, dt)
    except Exception as exc:  # noqa: BLE001 — STT is optional; TTS must still serve
        _state["whisper_error"] = str(exc)
        log.warning("whisper unavailable (%s). STT endpoints will 503.", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load off the event loop so startup does not block the port binding.
    await asyncio.gather(
        asyncio.to_thread(_load_voices),
        asyncio.to_thread(_load_whisper),
    )
    yield
    _state["voices"].clear()
    _state["whisper"] = None
    _state["asr"] = None


app = FastAPI(title="Bright speech", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SpeechRequest(BaseModel):
    input: str = Field(min_length=1, max_length=4000)
    voice: str = DEFAULT_VOICE
    # Per-sentence voice selection. On by default because a teacher line that
    # code-switches is the normal case here, not the exception. Turn it off to
    # force one voice over the whole line -- fixtures, or a deployment that
    # deliberately runs one language.
    segment: bool = True
    # OpenAI-compat fields we accept and ignore
    model: str | None = None
    response_format: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "voices": sorted(_state["voices"].keys()),
        "stt": bool(_state["whisper"]),
        "sttError": _state["whisper_error"],
        "sttModel": _state["whisper_model"] if _state["whisper"] else None,
        "sttModelsAvailable": _available_models(),
    }


class ModelRequest(BaseModel):
    model: str


@app.post("/admin/model")
async def set_model(req: ModelRequest) -> dict[str, Any]:
    """Swap the resident STT model without a restart.

    Exists so the room test (`tests/room/`) can A/B models against the *live*
    service rather than a private in-process copy, and so a bad demo-day choice
    is one curl away from being reverted. Local-only service, no auth: the
    allowlist is the guard — an unknown name is refused rather than becoming a
    download attempt in front of judges.

    Swapping is ~1-4 s (model load). In-flight transcriptions finish on the model
    they started with; there is no torn state, because inference reads the model
    reference once into a local.
    """
    name = req.model
    if name not in KNOWN_MODELS:
        raise HTTPException(400, f"unknown model {name!r}; known: {sorted(KNOWN_MODELS)}")
    if name not in _available_models():
        raise HTTPException(404, f"model {name!r} is not downloaded under {WHISPER_DIR}")

    async with _swap_lock:
        previous = _state["whisper_model"]
        if name == previous and _state["whisper"] is not None:
            return {"model": name, "previous": previous, "loadMs": 0, "changed": False}
        try:
            provider, dt = await asyncio.to_thread(_build_whisper, name)
        except Exception as exc:  # noqa: BLE001 — keep serving the old model
            log.error("model swap to %s failed: %s", name, exc)
            raise HTTPException(500, f"load failed: {exc}") from exc
        _state["asr"] = provider
        _state["whisper"] = provider       # compatibility alias
        _state["whisper_model"] = name
        _state["whisper_error"] = None
        log.info("swapped whisper %s -> %s in %.2fs", previous, name, dt)
        return {
            "model": name,
            "previous": previous,
            "loadMs": round(dt * 1000),
            "changed": True,
        }


# A letter that exists in Vietnamese and in no English word. Presence is a
# CERTAINTY, not a vote: counting Latin letters against Vietnamese ones marked
# "Chuối" as English, because a Vietnamese word is mostly plain Latin letters
# with one diacritic on it.
_VI_LETTER = re.compile(
    "[ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ"
    "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]"
)
# Sentence-ish boundaries, kept WITH the sentence they end.
_SENTENCE = re.compile(r"[^.!?…]*[.!?…]+[\"'”’)\]]*\s*|[^.!?…]+$")


def _voice_spans(text: str, *, default_voice: str, marked_voice: str) -> list[tuple[str, str]]:
    """Split one teacher line into (voice_id, text) runs, one per sentence.

    THE BUG THIS FIXES. Voice was picked once for a whole line, so a line that
    code-switches got ONE voice for all of it. Measured on lines she really
    said, 2026-08-20:

        "How are you? Mình khỏe, cảm ơn. Listen and say: Fine, thank you."
        "Không sao đâu. Say with me: Fine, thank you."

    Both contain a Vietnamese letter, so both were spoken entirely by the
    Vietnamese voice -- including "Listen and say: Fine, thank you.", which is
    the English pronunciation the child is supposed to copy. In a lesson whose
    whole point is the target language, the model utterance was wrong, and
    `say` never fails so no census could ever show it.

    Sentence granularity is the documented fallback in the code-switching
    research (section 11: "span synthesis using one closely matched voice"),
    chosen over per-word because "punctuation boundaries are forgiving" and
    her switches land on them. The cost is a prosody reset at each boundary,
    which is a pause a real teacher also takes between two languages.

    THE CHOICE IS BY SCRIPT, NOT BY "the other one". This first shipped as
    `other_voice = whichever voice is not the requested one`, which is only
    correct when the request asked for the un-marked voice. Build a Vietnamese
    fixture with `--voice vi` and every Vietnamese sentence was handed to the
    ENGLISH voice -- the exact defect this function exists to fix, running
    backwards. "Con không biết cô ạ" came back from ASR as
    'Concom BI letter 1EBT co letter 1E1', and it read as bad Vietnamese ASR
    rather than as bad Vietnamese audio. `marked_voice` is the voice for text
    carrying the marked script; `default_voice` speaks everything else.

    Not solved here, and named so nobody thinks it is: a Vietnamese sentence
    typed without diacritics still reads as English, and a switch INSIDE one
    sentence still takes one voice. The research's real answer is typed
    language spans carried down from the teacher, who already knows which span
    is which -- this is the boring fix that stops the bleeding meanwhile.
    """
    spans: list[tuple[str, str]] = []
    for match in _SENTENCE.finditer(text):
        chunk = match.group(0)
        if not chunk.strip():
            continue
        voice = marked_voice if _VI_LETTER.search(chunk) else default_voice
        if spans and spans[-1][0] == voice:
            spans[-1] = (voice, spans[-1][1] + chunk)
        else:
            spans.append((voice, chunk))
    return spans or [(default_voice, text)]


def _concat_wavs(chunks: list[bytes]) -> bytes:
    """Join same-format PCM WAVs into one. Piper voices share 16-bit mono output.

    Sample rates can differ between voices; refuse rather than emit audio that
    plays at the wrong pitch, and let the caller fall back to one voice.
    """
    if len(chunks) == 1:
        return chunks[0]
    params = None
    frames: list[bytes] = []
    for chunk in chunks:
        with wave.open(io.BytesIO(chunk), "rb") as wf:
            current = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate())
            if params is None:
                params = current
            elif current != params:
                raise ValueError(f"voice formats differ: {params} vs {current}")
            frames.append(wf.readframes(wf.getnframes()))
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(params[0])
        wf.setsampwidth(params[1])
        wf.setframerate(params[2])
        wf.writeframes(b"".join(frames))
    return out.getvalue()


def _synthesize(voice_id: str, text: str, speed: float) -> tuple[bytes, float]:
    voice = _state["voices"][voice_id]
    buf = io.BytesIO()
    t = time.perf_counter()
    kwargs: dict[str, Any] = {}
    if speed != 1.0:
        # piper length_scale is inverse of speed
        try:
            from piper import SynthesisConfig

            kwargs["syn_config"] = SynthesisConfig(length_scale=1.0 / speed)
        except Exception:  # noqa: BLE001 — older piper without SynthesisConfig
            pass
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf, **kwargs)
    return buf.getvalue(), time.perf_counter() - t


@app.post("/audio/speech")
async def speech(req: SpeechRequest) -> Response:
    request_started = time.perf_counter()
    voice_id = req.voice if req.voice in _state["voices"] else DEFAULT_VOICE
    if voice_id not in _state["voices"]:
        raise HTTPException(503, f"no voices loaded; wanted {req.voice!r}")

    # VieNeu speaks the whole line in one voice ON PURPOSE. Sentence splitting
    # exists because Piper needs a different voice per language and resets
    # prosody at every boundary; VieNeu handles the switch inside one utterance,
    # which is the entire reason it is here. Splitting it would throw that away.
    if TTS_ENGINE == "vieneu":
        try:
            spoken = await asyncio.to_thread(vieneu().synthesize, req.input, speed=req.speed)
        except Exception as exc:  # noqa: BLE001 -- she must never go mute
            log.warning("vieneu failed (%s); falling back to piper", exc)
        else:
            total_ms = round((time.perf_counter() - request_started) * 1000)
            return Response(
                content=spoken.audio,
                media_type="audio/wav",
                headers={
                    "X-Tts-Queue-Ms": "0",
                    "X-Synth-Ms": str(round(spoken.synth_s * 1000)),
                    "X-Tts-Total-Ms": str(total_ms),
                    "X-Voice": spoken.voice,
                    "X-Tts-Engine": "vieneu",
                    # 0ms synth means it came off disk -- the cache is the whole
                    # reason this engine is affordable, so make it visible.
                    "X-Tts-Cached": "1" if spoken.synth_s == 0.0 else "0",
                },
            )

    # One voice per SENTENCE, not one per line. A sentence carrying the marked
    # script goes to MARKED_VOICE; everything else goes to the requested voice.
    #
    # `default_voice` must not be the marked voice, or an un-marked sentence
    # inside a line the caller asked for in that voice never gets the other
    # one. A caller who wants the whole line in one voice says so with
    # `segment: false` -- that is what the flag is for, and it is what fixtures
    # and deliberate single-language deployments use.
    marked = MARKED_VOICE if MARKED_VOICE in _state["voices"] else voice_id
    plain = voice_id if voice_id != marked else DEFAULT_VOICE
    spans = (
        _voice_spans(req.input, default_voice=plain, marked_voice=marked)
        if req.segment and len(_state["voices"]) > 1
        else [(voice_id, req.input)]
    )

    queued = time.perf_counter()
    async with _tts_lock:
        queue_ms = round((time.perf_counter() - queued) * 1000)

        async def run() -> tuple[bytes, float]:
            pieces: list[bytes] = []
            spent = 0.0
            for span_voice, span_text in spans:
                chunk, elapsed = await asyncio.to_thread(
                    _synthesize, span_voice, span_text, req.speed
                )
                pieces.append(chunk)
                spent += elapsed
            try:
                return _concat_wavs(pieces), spent
            except ValueError as exc:
                # Voices disagree on sample rate. One voice at the wrong pitch
                # is worse than one voice in the wrong language, so fall back
                # rather than emit it.
                log.warning("cannot join spans (%s); using %s for the whole line", exc, voice_id)
                whole, elapsed = await asyncio.to_thread(
                    _synthesize, voice_id, req.input, req.speed
                )
                return whole, spent + elapsed

        inference = asyncio.create_task(run())
        try:
            data, dt = await asyncio.shield(inference)
        except asyncio.CancelledError:
            # Piper's native call cannot be interrupted. Retain the lock until
            # it exits so a cancelled HTTP request cannot enable concurrent
            # access to the shared ONNX session.
            await asyncio.shield(inference)
            raise

    synth_ms = round(dt * 1000)
    total_ms = round((time.perf_counter() - request_started) * 1000)
    log.info(
        "tts %s %dch -> %dB in %dms (%d queue + %d synth)",
        voice_id, len(req.input), len(data), total_ms, queue_ms, synth_ms,
    )
    return Response(
        content=data,
        media_type="audio/wav",
        headers={
            "X-Tts-Queue-Ms": str(queue_ms),
            "X-Synth-Ms": str(synth_ms),
            "X-Tts-Total-Ms": str(total_ms),
            "X-Voice": voice_id,
            "X-Tts-Engine": "piper",
        },
    )


@app.post("/audio/transcriptions")
async def transcriptions(
    request: Request,
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    languages: str | None = Form(default=None),
    model: str | None = Form(default=None),  # noqa: ARG001 — OpenAI-compat, ignored
) -> JSONResponse:
    request_started = time.perf_counter()
    if not _state["asr"]:
        raise HTTPException(503, f"stt unavailable: {_state['whisper_error']}")

    audio = await file.read(MAX_ASR_UPLOAD_BYTES + 1)
    if not audio:
        raise HTTPException(400, "empty audio")
    if len(audio) > MAX_ASR_UPLOAD_BYTES:
        raise HTTPException(413, "audio upload exceeds configured limit")

    # Read the model reference once: a concurrent /admin/model swap must not be
    # able to change it underneath a running transcription.
    provider: AsrProvider = _state["asr"]
    # Per-request `languages` (comma-separated) overrides the deployment
    # default ASR_LANGUAGES; classroom-core passes the real declared set once
    # it knows it. Ignored entirely when `language` is forced.
    allowed_languages = parse_languages(languages or ASR_LANGUAGES)
    queued = time.perf_counter()
    async with _asr_lock:
        queue_ms = round((time.perf_counter() - queued) * 1000)
        if await request.is_disconnected():
            raise HTTPException(499, "client disconnected before inference")
        inference = asyncio.create_task(
            asyncio.to_thread(
                provider.transcribe, audio, language=language, languages=allowed_languages
            )
        )
        try:
            asr_result = await asyncio.shield(inference)
        except asyncio.CancelledError:
            # The native inference thread cannot be killed safely. Keep the
            # lock until it exits so cancellation never enables concurrent use
            # of a provider that assumes one request at a time.
            await asyncio.shield(inference)
            raise
    total_ms = round((time.perf_counter() - request_started) * 1000)
    result = {
        "text": asr_result.text,
        "language": asr_result.language,
        "languageProbability": asr_result.language_probability,
        "confidence": asr_result.confidence,
        "noSpeechProbability": asr_result.no_speech_probability,
        "avgLogprob": asr_result.avg_logprob,
        "provider": type(provider).__name__,
        "model": provider.name,
        "ms": total_ms,
        "totalMs": total_ms,
        "queueMs": queue_ms,
        "decodeMs": asr_result.decode_ms,
        "inferMs": asr_result.infer_ms,
        "audioS": asr_result.audio_s,
    }
    log.info(
        "asr %dB %s (%s, %dms = %d queue + %d decode + %d infer; no-speech %.3f)",
        len(audio), result["model"], result["language"], result["ms"],
        result["queueMs"], result["decodeMs"], result["inferMs"],
        result["noSpeechProbability"],
    )
    return JSONResponse(result, headers={
        "X-Stt-Model": result["model"],
        "X-Asr-Queue-Ms": str(result["queueMs"]),
        "X-Asr-Infer-Ms": str(result["inferMs"]),
        "X-Asr-Total-Ms": str(result["totalMs"]),
    })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
