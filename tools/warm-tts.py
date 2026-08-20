#!/usr/bin/env python3
"""Render the unit's locked language into the TTS cache before the lesson.

VieNeu keeps Vietnamese tones through a code-switch, which Piper cannot, and
pays for it at RTF ~2. The cache makes that affordable: the price is per
DISTINCT line, not per utterance. Measured on this box:

    first time a line is spoken   6.55 s
    every repeat after that       0.011 s      600x

A unit's locked language is about ten sentences, and a period is mostly those
ten sentences. Warming them turns the expensive engine into a disk read for
most of a lesson, and leaves the slow path only for genuinely new speech.

This is a BUILD-TIME tool. It reads the curriculum; Core never does. It is the
same idea as the research's §10A ("pre-render authored curriculum speech"),
except the cache also covers dynamic lines once they have been said once.

    ./tools/warm-tts.py                       # every unit's locked language
    ./tools/warm-tts.py --also scripts/lines.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "speech"))

# The map prints its syllabus as a two-column table:  | Greet | Hello. / Hi. |
# Only the right-hand cell is language a teacher says out loud.
_ROW = re.compile(r"^\|[^|]+\|\s*(?P<said>[^|]+?)\s*\|\s*$")


# Sections of a unit map whose tables hold sentences a teacher says out loud.
# Nothing else in the map is warmed -- everything else is instructions to her.
_SPOKEN_SECTIONS = ("## locked language", "## arriving, and rescuing")

# Right-hand cells that are a table header, not something anyone says.
_HEADINGS = {"language", "function", "the one sentence you open with", "say exactly", "when"}


def locked_language(map_md: Path) -> list[str]:
    """Every utterance in the unit's spoken-language tables.

    Deliberately narrow: this reads NAMED sections, not the whole map. A tool
    that warmed every sentence in the curriculum would render the teacher's
    instructions and the author's notes as speech.

    The school-language arrival and rescue lines are here for the same reason
    as the locked target language: they are said verbatim, they are the FIRST
    thing anyone hears, and the engine that speaks them costs ~7 s cold and
    ~0.01 s warm. An unwarmed arrival line is seven seconds of silence at the
    top of a lesson.
    """
    lines: list[str] = []
    inside = False
    for raw in map_md.read_text(encoding="utf-8").splitlines():
        if raw.startswith("## "):
            inside = raw.strip().lower().startswith(_SPOKEN_SECTIONS)
            continue
        if not inside:
            continue
        match = _ROW.match(raw)
        if not match:
            continue
        cell = match.group("said")
        if set(cell) <= {"-", " ", ":"} or cell.lower().strip("* ") in _HEADINGS:
            continue
        # "Hello. / Hi." is two utterances, and "**h** in *hello*" is a note
        # about a sound rather than a sentence to say.
        # "Hello. / Hi." is two utterances; a whole school-language sentence is
        # not, and splitting one on a slash would cache half a greeting.
        parts = cell.split("/") if len(cell) < 40 else [cell]
        for part in parts:
            text = re.sub(r"[*`]", "", part).strip()
            # Skip anything she never says verbatim: a slot she fills with a
            # real name ("I'm [name].") and a note about sounds rather than a
            # sentence ("h in hello · b in bye"). Caching those spends the slow
            # engine on audio no lesson will ever play.
            if not text or "[" in text or "·" in text:
                continue
            lines.append(text)
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--also", help="extra lines, one per line")
    ap.add_argument("--voice", default=None, help="VieNeu preset (default: env VIENEU_VOICE)")
    ap.add_argument("--speech-url", default="http://127.0.0.1:8001",
                    help="the running speech service to warm through")
    ap.add_argument("--in-process", action="store_true",
                    help="load the provider here instead (needs the speech venv)")
    args = ap.parse_args()

    wanted: list[str] = []
    for map_md in sorted((ROOT / "content" / "library" / "units").glob("*/map.md")):
        found = locked_language(map_md)
        print(f"{map_md.parent.name}: {len(found)} locked utterances")
        wanted += found
    if args.also:
        wanted += [l.strip() for l in Path(args.also).read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.startswith("#")]

    # She streams, and the stage speaks each sentence as it arrives -- so the
    # cache key is a SENTENCE, not the line an author wrote. Measured 2026-08-21
    # on the opening turn: the whole arrival line was warm and the three
    # sentences it is actually said in were all cold, 18s of synthesis at the
    # top of the lesson. Warm both; the whole-line entry still covers a
    # deployment that ever sends one.
    pieces: list[str] = []
    for line in wanted:
        pieces.append(line)
        parts = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", line) if s.strip()]
        if len(parts) > 1:
            pieces += parts

    seen = list(dict.fromkeys(pieces))
    if not seen:
        print("nothing to warm")
        return 1

    for line in seen:
        print(f"  {line}")

    # Prefer the running service over an in-process provider. VieNeu's
    # phonemiser (`sea_g2p`) lives in the speech venv, not in whatever
    # interpreter runs this script, so importing the provider here fails on a
    # box where the service itself works perfectly. Going over HTTP also warms
    # the cache with the SAME engine, voice and speed the room will use --
    # the cache key is (engine, voice, text), so a mismatch would warm entries
    # nothing ever reads.
    if not args.in_process:
        import json
        import urllib.error
        import urllib.request

        url = args.speech_url.rstrip("/") + "/audio/speech"
        print(f"warming {len(seen)} distinct lines via {url}…")
        rendered = already = failed = 0
        for line in seen:
            body = json.dumps({"input": line}).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    if resp.headers.get("x-tts-cached") == "1":
                        already += 1
                    else:
                        rendered += 1
            except (urllib.error.URLError, OSError) as exc:
                failed += 1
                print(f"  ! {line[:40]}… {exc}")
        print(f"rendered {rendered}, already cached {already}, failed {failed}")
        return 1 if failed else 0

    from tts_vieneu import VieNeuProvider

    provider = VieNeuProvider(args.voice) if args.voice else VieNeuProvider()
    print(f"warming {len(seen)} distinct lines with {provider.name}…")
    result = provider.warm(seen)
    print(f"rendered {result['rendered']}, already cached {result['already']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
