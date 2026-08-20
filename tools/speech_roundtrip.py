#!/usr/bin/env python3
"""Measure TTS and ASR against each other, with no model credit spent.

The speech service is local and free. The teacher is not. So every question
about voice quality or hearing should be answered HERE, not by running a live
period and paying for a lesson to find out the microphone was wrong.

WHAT THIS CATCHES, all of it found the hard way:

  * a line synthesized in the wrong voice. "Say with me: Fine, thank you."
    spoken by the Vietnamese voice read back as 'Kosoco Sado, Sao Yume, Fai,
    Vakiu'. Nothing else in the system notices -- `say` never fails.
  * the mirror of it: Vietnamese handed to the English voice, which read back
    as 'Concom BI letter 1EBT co letter 1E1' and looked like an ASR problem.
  * a clip under the voice gate's MIN_CLIP_MS, which the room silently drops.

WHAT IT CANNOT ANSWER, and no machine can: whether it still sounds like ONE
teacher across a language switch, accent breaks, naturalness. The TTS
acceptance gate needs bilingual human raters (research §12). This measures
INTELLIGIBILITY -- if our own ASR cannot recover the words, a child certainly
cannot -- and that is a floor, not a pass.

    ./tools/speech_roundtrip.py                 # the curriculum's own lines
    ./tools/speech_roundtrip.py --say "..." --voice vi
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

SPEECH = "http://127.0.0.1:8001"
MIN_CLIP_MS = 600

# The unit's locked language, plus the code-switching shapes she really
# produces. Every mixed line here is verbatim from a live period's logs.
CORPUS: list[tuple[str, str]] = [
    ("en", "Hello. I'm Ben."),
    ("en", "How are you?"),
    ("en", "Fine, thank you."),
    ("en", "Goodbye."),
    ("en", "Listen and repeat: Fine, thank you."),
    ("vi", "Con chưa hiểu bài này"),
    ("vi", "Con không biết cô ạ"),
    ("vi", "Không sao đâu."),
    ("mix", "Không sao đâu. Say with me: Fine, thank you."),
    ("mix", "How are you? Mình khỏe, cảm ơn. Listen and say: Fine, thank you."),
]


def _post(path: str, *, data: bytes | None = None, headers: dict | None = None, timeout=300):
    req = urllib.request.Request(SPEECH + path, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        # r.headers is an email.Message: case-insensitive .get, unlike dict().
        return r.read(), r.headers


def synthesize(text: str, voice: str | None) -> tuple[bytes, int, str]:
    body = {"input": text}
    if voice:
        body["voice"] = voice
    audio, headers = _post(
        "/audio/speech",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    return audio, int(headers.get("X-Synth-Ms", 0)), headers.get("X-Voice", "?")


def transcribe(audio: bytes, language: str | None = None) -> tuple[str, str, int]:
    boundary = "----bright"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode() + audio + b"\r\n"
    ]
    if language:
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\""
            f"\r\n\r\n{language}\r\n".encode()
        )
    parts.append(f"--{boundary}--\r\n".encode())
    started = time.perf_counter()
    raw, _ = _post(
        "/audio/transcriptions",
        data=b"".join(parts),
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    got = json.loads(raw)
    return got.get("text", "").strip(), got.get("language", "?"), round(
        (time.perf_counter() - started) * 1000
    )


def _words(text: str) -> set[str]:
    return {w for w in re.sub(r"[^\w\sÀ-ỹ]", " ", text.lower()).split() if len(w) > 1}


def score(said: str, heard: str) -> tuple[int, int]:
    want, got = _words(said), _words(heard)
    return len(want & got), len(want)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--say", help="one line instead of the corpus")
    ap.add_argument("--voice", help="force a voice (default: the service decides per sentence)")
    args = ap.parse_args()

    corpus = [("adhoc", args.say)] if args.say else CORPUS
    rows, total_hit, total_want = [], 0, 0

    print(f"{'kind':5} {'voice':6} {'tts':>6} {'asr':>7} {'lang':4} {'words':>7}  line / heard")
    print("-" * 100)
    for kind, text in corpus:
        try:
            audio, tts_ms, voice = synthesize(text, args.voice)
        except Exception as exc:  # noqa: BLE001 -- a dead service is the finding
            print(f"{kind:5} SYNTH FAILED: {exc}")
            return 2
        # 44 bytes of WAV header, 16-bit mono; good enough to spot a clip the
        # room's own gate would refuse before it ever reaches Whisper.
        ms = round((len(audio) - 44) / 2 / 22050 * 1000)
        heard, lang, asr_ms = transcribe(audio)
        hit, want = score(text, heard)
        total_hit, total_want = total_hit + hit, total_want + want
        flag = "  <- UNDER THE GATE'S FLOOR" if ms < MIN_CLIP_MS else ""
        print(f"{kind:5} {voice:6} {tts_ms:5}ms {asr_ms:6}ms {lang:4} {hit:3}/{want:<3}  {text}")
        print(f"{'':5} {'':6} {'':7} {'':7} {'':4} {'':7}  -> {heard!r}{flag}")
        rows.append({"kind": kind, "said": text, "heard": heard, "voice": voice,
                     "language": lang, "ttsMs": tts_ms, "asrMs": asr_ms,
                     "clipMs": ms, "hit": hit, "want": want})

    print("-" * 100)
    pct = (100 * total_hit / total_want) if total_want else 0
    print(f"content words recovered: {total_hit}/{total_want}  ({pct:.0f}%)")
    print("This is an intelligibility floor, not the acceptance gate. Speaker")
    print("similarity, accent breaks and naturalness need human ears (research §12).")
    Path("/tmp/speech_roundtrip.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
