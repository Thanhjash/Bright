#!/usr/bin/env python3
"""Build the WAV Chromium plays as a fake microphone for a WHOLE conversation.

`build_voice_gate_wav.py` makes one utterance, and one utterance is all any
speech test in this repo has ever driven. The thing a child actually does is
speak, listen to the answer, and speak again -- and turn two has never been
exercised through the microphone at all.

WHY ONE FILE AND NOT ONE PER LINE. Chromium takes
`--use-file-for-fake-audio-capture` as a *launch* flag and restarts it at offset
0 on every fresh `getUserMedia`, so one browser can only ever play one
recording. Relaunching per line would drop the Stage's audio lease, and the
room would close and reopen between every sentence. So the whole pupil side of
the lesson goes into one file, with silence where the teacher answers.

That is not a workaround pretending to be a design. It is what the room sounds
like from the child's chair: the child speaks, the room is quiet while the
teacher talks, the child speaks again.

The gap has to be longer than she takes to answer, or her reply is still
playing when the next pupil line arrives and half-duplex gating drops it. The
defaults below are measured, not chosen -- see GAP_MS.

    ./tools/build_pupil_conversation.py --script scripts/pupils/spoken.txt -o /tmp/pupil.wav

Prints one JSON line with the exact span of every line, so a harness knows when
each was spoken and can attribute what it sees on the network:

    {"path": "...", "gapMs": 45000, "firstGapMs": 95000, "totalMs": 411200,
     "lines": [{"n": 1, "say": "Hello teacher", "voice": "en",
                "startMs": 1400, "speechMs": 987}, ...]}
"""
from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_voice_gate_wav import PAD_MS, RATE, _to_mono_16k, _tts  # noqa: E402

# Long enough for her reply plus the gate re-arming after she stops talking.
# Measured on the first spoken conversation, 2026-08-20, as the wait from "the
# child's words reached ASR" to "she started speaking":
#
#     turn 1   75.7s        <- opening the class: reads the map, writes a plan
#     turn 2   23.3s
#     turn 3+  18.3 - 19.8s  and still falling
#
# Her speaking time comes on top, and the microphone is closed while she talks
# (half-duplex, so she cannot transcribe herself). With a flat 40s gap the
# child's SECOND sentence landed inside her first reply and was simply lost.
#
# So the first gap is its own number. A human sitting in the chair does not
# need this -- they wait for her to finish -- but a recording cannot wait.
GAP_MS = 45_000
FIRST_GAP_MS = 95_000
MIN_CLIP_MS = 600


def _silence(ms: int) -> bytes:
    """Digital silence, not noise.

    The gate's noise floor adapts upward from whatever it hears, so a hissy pad
    would raise the bar the child's own speech has to clear.
    """
    return b"\x00\x00" * int(RATE * ms / 1000)


def _parse_script(path: Path) -> list[tuple[str, str]]:
    """`voice: text` per line. `#` comments, blank lines ignored.

    The voice is explicit rather than detected, because this file is the
    *child's* side and a Vietnamese line from a Grade-3 beginner is exactly the
    case automatic detection gets wrong.
    """
    out: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        voice, _, text = line.partition(":")
        voice, text = voice.strip().lower(), text.strip()
        if voice not in {"en", "vi"} or not text:
            raise SystemExit(f"bad script line (want `en: ...` or `vi: ...`): {raw!r}")
        out.append((voice, text))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True, help="one `en: ...` / `vi: ...` per line")
    ap.add_argument("--gap-ms", type=int, default=GAP_MS, help="quiet for her reply")
    ap.add_argument(
        "--first-gap-ms", type=int, default=FIRST_GAP_MS,
        help="quiet after line 1, which she spends opening the class",
    )
    ap.add_argument("--pad-ms", type=int, default=PAD_MS, help="lead-in before the first line")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    script = _parse_script(Path(args.script))
    if not script:
        raise SystemExit("script has no lines")

    frames = bytearray(_silence(args.pad_ms))
    spans: list[dict] = []
    for index, (voice, text) in enumerate(script, start=1):
        speech, speech_ms = _to_mono_16k(_tts(text, voice))
        if speech_ms < MIN_CLIP_MS:
            raise SystemExit(
                f"line {index} is {speech_ms}ms, under the gate's MIN_CLIP_MS of "
                f"{MIN_CLIP_MS}: {text!r}. Whisper invents words on takes that short."
            )
        spans.append({
            "n": index,
            "say": text,
            "voice": voice,
            "startMs": round(len(frames) / 2 / RATE * 1000),
            "speechMs": speech_ms,
        })
        frames += speech
        # The last line gets a gap too: she answers it, and the harness needs
        # to still be listening when she does.
        frames += _silence(args.first_gap_ms if index == 1 else args.gap_ms)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(bytes(frames))

    print(json.dumps({
        "path": str(out.resolve()),
        "gapMs": args.gap_ms,
        "firstGapMs": args.first_gap_ms,
        "padMs": args.pad_ms,
        "totalMs": round(len(frames) / 2 / RATE * 1000),
        "lines": spans,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
