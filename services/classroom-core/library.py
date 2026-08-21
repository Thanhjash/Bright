"""Scoped curriculum library. Hermes may read only this tree."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from config import REPO_ROOT

LIBRARY_ROOT = REPO_ROOT / "content" / "library"
_ASSET = re.compile(r"asset://[a-z0-9_./-]+", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class LibraryError(ValueError):
    """Path is outside the library or not a readable markdown file."""


def resolve_library_path(raw: str, *, root: Path | None = None) -> Path:
    base = (root or LIBRARY_ROOT).resolve()
    text = (raw or "").strip().lstrip("/")
    if not text or ".." in Path(text).parts:
        raise LibraryError("path escapes the library")
    target = (base / text).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise LibraryError("path escapes the library") from exc
    if not target.is_file() or target.suffix.lower() != ".md":
        raise LibraryError("library file not found")
    return target


def read_library(raw: str, *, root: Path | None = None, limit: int = 8000) -> dict[str, str]:
    path = resolve_library_path(raw, root=root)
    body = path.read_text(encoding="utf-8")[:limit]
    base = (root or LIBRARY_ROOT).resolve()
    return {"path": str(path.relative_to(base)).replace("\\", "/"), "text": body}


def _snippet_around(body: str, needles: list[str], width: int = 240) -> str:
    """The text around the first match, not the top of the file.

    A search result whose snippet is always the document's opening paragraph
    says which file matched and nothing about why, so the reader has to open
    the whole file anyway -- which is the cost search exists to avoid.
    """
    flat = " ".join(body.split())
    low = flat.lower()
    # Anchor on the rarest term, not the earliest one. Searching "Fine thank
    # you" must not centre on the first stray "you" in the opening sentence.
    hit = -1
    for tok in sorted(set(needles), key=lambda t: (low.count(t), -len(t))):
        found = low.find(tok)
        if found >= 0:
            hit = found
            break
    if hit < 0:
        return flat[:width]
    start = max(0, hit - width // 3)
    text = flat[start : start + width]
    return ("\u2026" + text) if start else text


def search_library(query: str, *, root: Path | None = None, limit: int = 5) -> dict[str, object]:
    q = " ".join((query or "").split())
    if not q:
        raise LibraryError("query is empty")
    base = (root or LIBRARY_ROOT).resolve()
    if not base.is_dir():
        raise LibraryError("library file not found")
    needles = [tok.lower() for tok in _TOKEN.findall(q)]
    scored: list[tuple[int, str, str, list[str]]] = []
    for path in sorted(base.rglob("*.md")):
        try:
            path.relative_to(base)
        except ValueError:
            continue
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8")
        low = body.lower()
        score = sum(low.count(tok) for tok in needles) if needles else 0
        if score <= 0:
            continue
        rel = str(path.relative_to(base)).replace("\\", "/")
        snippet = _snippet_around(body, needles)
        assets = list(dict.fromkeys(_ASSET.findall(body)))
        scored.append((score, rel, snippet, assets))
    scored.sort(key=lambda row: (-row[0], row[1]))
    hits = [
        {"path": rel, "snippet": snippet, "assets": assets}
        for _score, rel, snippet, assets in scored[: max(1, min(limit, 5))]
    ]
    return {"hits": hits}


# An objective is DECLARED, with `id:` in front of it. Anything else that
# happens to be a backticked hyphenated word is not one.
_OBJECTIVE_ID = re.compile(r"id:\s*`([a-z][a-z0-9-]{2,})`")
# A loose reference to an id, for prose that MENTIONS objectives rather than
# declaring them -- `Objectives in play: \`greet-and-name\`, ...`. Correct there,
# and only there: it cannot tell an objective from any other backticked token.
_OBJECTIVE_REF = re.compile(r"`([a-z]+-[a-z0-9-]+)`")


def list_units(*, root: Path | None = None) -> list[str]:
    """Every unit folder on disk, sorted. Core must never name a lesson itself.

    Which unit is taught is a property of the appliance's content, not of the
    software (NS-7). If exactly one unit is authored, that is the default; if
    several are, the adult picks one and nothing in code prefers a favourite.
    """
    base = ((root or LIBRARY_ROOT) / "units").resolve()
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir() if d.is_dir() and any(d.glob("*.md")))


_TZ = re.compile(r"^-\s*`?timezone:\s*([A-Za-z0-9_+\-/]+)`?", re.M)
_PREPARE_AT = re.compile(r"^-\s*`?prepare_at:\s*([0-2]?\d:[0-5]\d)`?", re.M)
_PERIODS = re.compile(r"^-\s*`?periods:\s*([0-9:,\s]*)`?", re.M)


def timetable(*, root: Path | None = None) -> dict[str, Any]:
    """When this school's periods are, as the deployment declares them.

    NS-7: the deployment declares itself, and a timetable is on the list of
    things it declares. Until 2026-08-20 nothing in the system knew what time a
    class was -- `REOPEN_AFTER_CLOSE_S = 600` was the entire stand-in for a
    school day, and the nightly preparation ran on a hardcoded hour in UTC,
    which in the first deployment is ten in the morning.

    Parsed, never interpreted. Core uses it to set a clock; it reads no meaning
    into the numbers, and an empty or missing declaration is not an error -- the
    room simply falls back to opening when someone appears.
    """
    index = (root or LIBRARY_ROOT) / "index.md"
    try:
        text = index.read_text(encoding="utf-8")
    except OSError:
        return {"timezone": None, "prepare_at": None, "periods": []}
    tz = _TZ.search(text)
    at = _PREPARE_AT.search(text)
    periods = _PERIODS.search(text)
    return {
        "timezone": tz.group(1) if tz else None,
        "prepare_at": at.group(1) if at else None,
        "periods": [p.strip() for p in (periods.group(1) if periods else "").split(",") if p.strip()],
    }


def unit_catalog(unit_id: str, *, root: Path | None = None) -> dict[str, list[str]]:
    """Objectives and asset:// ids printed in one unit folder. No extra semantics."""
    name = (unit_id or "").strip()
    if not name or ".." in name or "/" in name:
        return {"objectives": [], "assets": []}
    base = ((root or LIBRARY_ROOT) / "units" / name).resolve()
    library = (root or LIBRARY_ROOT).resolve()
    try:
        base.relative_to(library)
    except ValueError:
        return {"objectives": [], "assets": []}
    if not base.is_dir():
        return {"objectives": [], "assets": []}
    objectives: set[str] = set()
    assets: set[str] = set()
    for path in sorted(base.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assets.update(_ASSET.findall(text))
        # DECLARED objectives only.
        #
        # This used to union the loose reference pattern as well, so anything
        # backticked with a hyphen in it became an objective: measured on the one
        # authored unit, `scaffold-down` (a skill) and `track-09` (an audio file)
        # were both offered to her as things to teach, and `record_evidence`'s
        # allow-list accepted them -- a child's progress recordable against a
        # sound file. Six declared, eight shipped.
        objectives.update(_OBJECTIVE_ID.findall(text))
    return {"objectives": sorted(objectives), "assets": sorted(set(assets))}


# `### Period 1 — Hello, I'm …` — the number and the title an author wrote.
# Em dash or hyphen, because both get typed.
_PERIOD_HEAD = re.compile(r"^###\s*Period\s+(\d+)\s*[—\-–]\s*(.+?)\s*$", re.M)
# `Objectives in play: \`greet-and-name\`, \`answer-a-greeting\`.`
_IN_PLAY = re.compile(r"^Objectives in play:\s*(.+?)\s*$", re.M)
# `Card picture: \`asset://gs3/panels/char-minh.jpg\`` — the picture the front
# door shows for this period. Chosen by the unit's author, never by the app:
# which face belongs to "How are you? Goodbye" is curriculum, and a UI that
# picked one would be software deciding what a lesson looks like.
_CARD_ART = re.compile(r"^Card picture:\s*`(asset://[^`]+)`", re.M)


# `| b | Để cô nghĩ chút nhé. |` under `**The holding lines.**` -- the right-hand
# cell is the sentence, the left is only a label so an author can talk about one.
_HOLDING_HEAD = re.compile(r"^\*\*The holding lines\.\*\*", re.M)
_TABLE_ROW = re.compile(r"^\|[^|]+\|\s*(?P<said>[^|]+?)\s*\|\s*$", re.M)


def holding_lines(unit_id: str, *, root: Path | None = None) -> list[str]:
    """The sentences the ROOM says while she is thinking. Parsed, never judged.

    The only text in this system that becomes speech without the model in the
    loop -- which is the point, because it exists to cover the wait FOR the
    model. That makes the rule it lives under worth stating: **Core may quote
    the curriculum; Core may never compose.** These are read verbatim from the
    unit map, exactly as `list_periods` reads period titles and card art, and
    exactly as an arrival line is read. Nothing here writes a sentence.

    Returns [] for a unit with no such table, and the room then says nothing --
    which is what it did before these existed. Never raises: a missing holding
    line must not cost a turn.
    """
    name = (unit_id or "").strip()
    if not name or ".." in name or "/" in name:
        return []
    base = ((root or LIBRARY_ROOT) / "units" / name).resolve()
    library = (root or LIBRARY_ROOT).resolve()
    try:
        base.relative_to(library)
    except ValueError:
        return []
    map_md = base / "map.md"
    if not map_md.is_file():
        return []
    text = map_md.read_text(encoding="utf-8")

    head = _HOLDING_HEAD.search(text)
    if not head:
        return []
    # From the paragraph that introduces them to the next section heading. The
    # section sits among other tables (locked language, arrival, rescue) and
    # taking the wrong one would put a syllabus item in a child's ear as though
    # the room had answered them.
    end = text.find("\n## ", head.end())
    body = text[head.end(): end if end != -1 else len(text)]

    lines: list[str] = []
    for row in _TABLE_ROW.finditer(body):
        said = row.group("said").strip()
        # The header row, and the `|---|---|` rule under it.
        if not said or set(said) <= {"-", " ", ":"} or said.lower() == "say exactly":
            continue
        lines.append(said)
    return lines


def list_periods(unit_id: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    """The periods an author wrote in a unit map, in order. Parsed, never judged.

    A period is `### Period N — Title` in `map.md`, with the objectives it puts
    in play named beneath it. Core reads the number and the words; it reads no
    meaning into either. Which period comes next, whether one is finished, and
    what a title implies are all somebody else's questions -- the teacher's, or
    the lobby's, from evidence Core already keeps.

    Returns [] for a unit with no map or no period headings rather than raising:
    a unit is allowed to be one long lesson, and the front door simply has
    nothing to list for it.
    """
    name = (unit_id or "").strip()
    if not name or ".." in name or "/" in name:
        return []
    base = ((root or LIBRARY_ROOT) / "units" / name).resolve()
    library = (root or LIBRARY_ROOT).resolve()
    try:
        base.relative_to(library)
    except ValueError:
        return []
    map_md = base / "map.md"
    if not map_md.is_file():
        return []
    text = map_md.read_text(encoding="utf-8")

    heads = list(_PERIOD_HEAD.finditer(text))
    periods: list[dict[str, Any]] = []
    for i, head in enumerate(heads):
        body = text[head.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        in_play = _IN_PLAY.search(body)
        objectives = _OBJECTIVE_REF.findall(in_play.group(1)) if in_play else []
        art = _CARD_ART.search(body)
        periods.append({
            "n": int(head.group(1)),
            "title": head.group(2).strip(),
            "objectives": objectives,
            # The author's own words as well as the ids. Period 3 says "all of
            # them, plus `hear-h-and-b`" -- the ids alone would render that
            # period as the single narrowest thing in the unit, which is the
            # opposite of what it is.
            "inPlay": in_play.group(1).rstrip(".").strip() if in_play else "",
            "art": art.group(1) if art else "",
        })
    return periods
