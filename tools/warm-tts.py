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


def locked_language(map_md: Path) -> list[str]:
    """Every utterance in the unit's `## Locked language` table.

    Deliberately narrow: this reads ONE named section, not the whole map. A
    tool that warms every sentence in the curriculum would render the teacher's
    instructions and the author's notes as speech.
    """
    lines: list[str] = []
    inside = False
    for raw in map_md.read_text(encoding="utf-8").splitlines():
        if raw.startswith("## "):
            inside = raw.strip().lower().startswith("## locked language")
            continue
        if not inside:
            continue
        match = _ROW.match(raw)
        if not match:
            continue
        cell = match.group("said")
        if set(cell) <= {"-", " ", ":"} or cell.lower() in {"language", "function"}:
            continue
        # "Hello. / Hi." is two utterances, and "**h** in *hello*" is a note
        # about a sound rather than a sentence to say.
        for part in cell.split("/"):
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
    args = ap.parse_args()

    wanted: list[str] = []
    for map_md in sorted((ROOT / "content" / "library" / "units").glob("*/map.md")):
        found = locked_language(map_md)
        print(f"{map_md.parent.name}: {len(found)} locked utterances")
        wanted += found
    if args.also:
        wanted += [l.strip() for l in Path(args.also).read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.startswith("#")]

    seen = list(dict.fromkeys(wanted))
    if not seen:
        print("nothing to warm")
        return 1

    from tts_vieneu import VieNeuProvider

    provider = VieNeuProvider(args.voice) if args.voice else VieNeuProvider()
    print(f"warming {len(seen)} distinct lines with {provider.name}…")
    for line in seen:
        print(f"  {line}")
    result = provider.warm(seen)
    print(f"rendered {result['rendered']}, already cached {result['already']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
