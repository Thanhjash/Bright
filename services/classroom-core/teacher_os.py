"""Classroom OS for the teacher-agent loop. Not a lesson graph."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from functools import lru_cache
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

from config import REPO_ROOT
from library import LibraryError, read_library, search_library, unit_catalog

log = logging.getLogger("bright.teacher")

OUTCOMES = frozenset({"correct", "wrong", "uncertain", "near"})
# NORTH-STAR §1. Short on purpose: a teacher who escalates constantly is not
# autonomous either.
ESCALATION_REASONS = frozenset(
    {"danger", "distress", "disclosure", "equipment", "cannot_reach_the_class"}
)
MODES = frozenset({"name", "point", "ask"})
ATTEMPT_MODES = frozenset({"name", "point"})
# Case-insensitive. A class-wide answer is not one learner's evidence.
PLACEHOLDER_STUDENT_IDS = frozenset({"class", "everyone", "choral", "all"})
_ASSET = re.compile(r"^asset://[a-z0-9][a-z0-9_./-]*$", re.IGNORECASE)
_MEDIA_ROOT = (REPO_ROOT / "content" / "media").resolve()
UNSAFE = re.compile(
    r"\b(?:correct|incorrect|wrong|right answer|well done|good job|"
    r"you(?:'re| are) right|you(?:'re| are) wrong)\b",
    re.IGNORECASE,
)
BOARD_GRADE = re.compile(
    r"(?:[✓✔✅❌☑✗]|you said it)",
    re.IGNORECASE,
)


PLAN_MAX_CHARS = 1200
BOARD_MAX_CHARS = 400
BOARD_MAX_LINES = 8

# OpenClaw-style main-session pulse. Not the 5 s WebSocket ping.
SYSTEM_EVENTS = {
    "[sat_down]": "class_start",
    "[heartbeat]": "heartbeat",
    "[prepare]": "prepare",
    "[wake]": "wake",
    "[floor]": "floor",
}
# She may ask the room to wake her. Without it there is structurally no such
# thing as an ACTIVITY: her only wakes are a child speaking, one 7s nudge, and
# a 45s silence floor -- so "say it together, three times, listening between
# each" is three rounds of a silent classroom, and she simply never starts one.
WAKE_MIN_S = 5.0
WAKE_MAX_S = 180.0
# Before class the room is empty and the projector is dark. A preparation turn
# may read the library and write her plan; it may not speak, put anything on
# the board, or record evidence about a child who is not there. Enforced in
# `execute` rather than in the prompt, because "the Stage is the only
# loudspeaker" is not a thing to ask an agent nicely for.
PREPARE_TOOLS = frozenset({"read_library", "search_library", "read_board", "plan"})
HEARTBEAT_OK = "HEARTBEAT_OK"
# The unit map says "Four seconds of wait after a question -- count it."
# HEARTBEAT_SILENCE_S is the wait for a room that has simply gone quiet; it is
# far too long for a child who was just asked something and is thinking. So the
# wait is not one constant: it is a property of what she last did.
#
# One nudge, then back to the long floor -- ask, count to four, nudge once,
# move on. Prompting every few seconds would be nagging, and on a local model
# every prompt is CPU we own.
WAIT_AFTER_QUESTION_S = 7.0
# Two different silences, and treating them as one is why a period lasted three
# minutes. When she has ASKED something, quiet means the class is thinking and
# 45s is the right patience. When she has NOT, quiet means the floor is hers and
# nobody is coming -- waiting 45s there is a teacher standing at the front of a
# room doing nothing. Measured 2026-08-19: 84 heartbeats, every one of them a
# single line or the null answer.
HEARTBEAT_SILENCE_S = 45.0
HEARTBEAT_FLOOR_IS_HERS_S = 12.0
HEARTBEAT_MIN_GAP_S = 20.0
HEARTBEAT_TICK_S = 10.0


# Scripts the room may see. NS-7 says software never names a language, so this
# is not a list of languages -- it is derived from the appliance's own authored
# curriculum. Whatever writing systems the library is written in are the ones
# this classroom reads; anything else is the model leaking, not the teacher
# teaching.
#
# Observed live 2026-08-18: the hosted Chinese model wrote
# "不用唱出来，听听就好～" onto the projector in a Vietnamese classroom. A prompt
# instruction is not a control for this. Core refuses it, and she rewrites
# inside the same turn.
_SCRIPT_RANGES: tuple[tuple[str, int, int], ...] = (
    ("latin", 0x0041, 0x024F),
    ("latin", 0x1E00, 0x1EFF),   # Vietnamese diacritics live here
    ("greek", 0x0370, 0x03FF),
    ("cyrillic", 0x0400, 0x04FF),
    ("arabic", 0x0600, 0x06FF),
    ("devanagari", 0x0900, 0x097F),
    ("thai", 0x0E00, 0x0E7F),
    ("hangul", 0xAC00, 0xD7AF),
    ("hiragana", 0x3040, 0x309F),
    ("katakana", 0x30A0, 0x30FF),
    ("han", 0x3400, 0x4DBF),
    ("han", 0x4E00, 0x9FFF),
)


# Romanised Chinese wears Latin clothes. DeepSeek opened a lesson with
# "Mǐnggué zō bànguàng" -- pinyin, so _SCRIPT_RANGES sees only "latin" and lets
# it through. The caron and the macron are the tell: pinyin uses ǎ ǐ ǒ ǔ ě and
# ā ē ī ō ū, and Vietnamese uses neither. Vietnamese tone marks are acute,
# grave, hook, tilde and dot-below, none of which appear here.
_PINYIN_TONES = frozenset("āēīōūǖáǎǐǒǔǚàǀěĂăĀĒĪŌŪǍǏǑǓĚ") - frozenset("ĂăÀàÁá")


def _script_of(ch: str) -> str | None:
    """The writing system of one character, or None for script-neutral text.

    Digits, punctuation, whitespace and emoji belong to every language, so they
    are never a reason to refuse a board.
    """
    code = ord(ch)
    for name, low, high in _SCRIPT_RANGES:
        if low <= code <= high:
            return name
    return None


@lru_cache(maxsize=1)
def _library_scripts() -> frozenset[str]:
    """Every writing system the authored curriculum actually uses."""
    from library import LIBRARY_ROOT

    found: set[str] = set()
    try:
        for md in LIBRARY_ROOT.rglob("*.md"):
            for ch in md.read_text(encoding="utf-8"):
                script = _script_of(ch)
                if script:
                    found.add(script)
    except OSError:
        return frozenset({"latin"})
    return frozenset(found or {"latin"})


def _alien_script(text: str) -> str | None:
    """The first writing system in `text` that this appliance does not teach."""
    allowed = _library_scripts()
    for ch in text:
        if ch in _PINYIN_TONES and "han" not in allowed:
            return "romanised chinese"
        script = _script_of(ch)
        if script and script not in allowed:
            return script
    return None


def _clean_board_markdown(raw: str) -> str | None:
    """Safe chalkboard markdown: headings, lists, emphasis. No HTML or URLs."""
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    if re.search(r"https?://|www\.|<[^>]+>", text, re.IGNORECASE):
        return None
    lines: list[str] = []
    blank = False
    for line in text.split("\n"):
        cleaned = line.rstrip()
        if not cleaned.strip():
            if lines and not blank:
                lines.append("")
                blank = True
            continue
        blank = False
        lines.append(cleaned)
        if len(lines) >= BOARD_MAX_LINES:
            break
    body = "\n".join(lines).strip()
    if not body or len(body) > BOARD_MAX_CHARS:
        return None
    if UNSAFE.search(body) or BOARD_GRADE.search(body):
        return None
    if _alien_script(body):
        return None
    return body


_REASON_CLASSES: tuple[tuple[str, str], ...] = (
    ("script", "alien-script"),
    ("non-evaluative", "grade-word"),
    ("URL", "url-or-markup"),
    ("characters", "length"),
    ("chars", "length"),
    ("not found", "asset-missing"),
    ("asset://", "asset-malformed"),
    ("objective", "objective"),
    ("learner", "attribution"),
    ("student", "attribution"),
    ("heartbeat", "heartbeat"),
)


def _reason_class(reason: str) -> str:
    """Bucket a refusal into a countable slug.

    Every refusal string in this file is authored here, so none of them carry
    a child's words -- but logging counts instead of sentences keeps that true
    by construction rather than by review.
    """
    text = (reason or "").lower()
    for needle, slug in _REASON_CLASSES:
        if needle.lower() in text:
            return slug
    return "other"


def _asset_name(raw: Any) -> str:
    """`asset://gs3/audio/track-05.mp3` -> `track-05`. Short enough for a log line."""
    text = str(raw or "").strip()
    if not text:
        return ""
    tail = text.rsplit("/", 1)[-1]
    return tail.rsplit(".", 1)[0] or tail


def _board_refusal(raw: str, label: str) -> str:
    """Why _clean_board_markdown refused this text, in words she can act on.

    A bare "it did not apply" teaches her nothing and she repeats it next turn.
    _check_free_text already names the specific fault -- alien script, a grade
    word, a URL -- so reuse it and fall back to the grammar only when it finds
    nothing more specific.
    """
    return _check_free_text(
        raw, min_len=1, max_len=BOARD_MAX_CHARS, label=label
    ) or (
        f"{label} must be 1..{BOARD_MAX_CHARS} chars, {BOARD_MAX_LINES} lines, "
        "no URL or HTML"
    )


def _check_free_text(text: str, *, min_len: int, max_len: int, label: str) -> str | None:
    """Shared non-evaluative / no-HTML / no-URL check for every board string.

    ``write_board``, ``say`` and every free-text field inside a
    ``show_exercise`` payload land on the same projected board, so the ban on
    a grade (``✓`` / "correct" / "well done") does not stop applying because
    the tool name changed. Do not reimplement this per-field.
    """
    line = " ".join((text or "").split())
    if len(line) < min_len or len(line) > max_len:
        return f"{label} must be {min_len}..{max_len} characters"
    if UNSAFE.search(line):
        return f"{label} must be non-evaluative"
    if re.search(r"https?://|www\.|<[^>]+>", line, re.IGNORECASE):
        return f"{label} contains URL or markup"
    alien = _alien_script(line)
    if alien:
        # Say it in the languages this classroom actually reads, so she can
        # rewrite inside the same turn instead of losing the move.
        return (
            f"{label} uses {alien} script, which this classroom does not read -- "
            f"write it in the languages the library uses"
        )
    return None


def _check_teacher_line(text: str) -> str | None:
    return _check_free_text(text, min_len=1, max_len=220, label="teacher_line")


def _is_heartbeat_ok(text: str) -> bool:
    line = " ".join((text or "").split()).upper()
    return line == HEARTBEAT_OK or line.startswith(HEARTBEAT_OK + " ")


def probe_http(url: str, timeout_s: float = 0.4) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def hermes_up() -> bool:
    base = os.environ.get("HERMES_API_URL", "http://127.0.0.1:8642").rstrip("/")
    return probe_http(base + "/health")


def speech_up() -> bool:
    base = os.environ.get("SPEECH_URL", "http://127.0.0.1:8001").rstrip("/")
    return probe_http(base + "/health")


def system_event(text: str) -> str | None:
    return SYSTEM_EVENTS.get(" ".join((text or "").split()))


def _as_asset(raw: str) -> str | None:
    text = str(raw or "").strip()
    if ".." in text or not _ASSET.match(text):
        return None
    return text


def _caption_for_board(line: str | None, limit: int = 160) -> str:
    """The line under a picture: whole if it fits, and NEVER cut mid-word.

    This was `[:80]`, which put

        "Chào các con! Cô là cô Bright. Hôm nay mình học cách chào nhau và nói
         tên mình b"

    on a projector in front of a class -- a sentence amputated inside its last
    word. A cut word is worse than a shortened caption and much worse than
    none: a child reading a board sounds out what is written, and "b" is not a
    word in any of this room's three languages.

    80 was also simply too small. The caption wraps (`ImageBoard`'s figcaption
    is `max-w-[90%]` with normal wrapping), so two lines of ordinary teacher
    speech fit comfortably; 160 is that, measured against the board's width at
    the caption's own type size. Past it, cut at a word boundary and say so
    with an ellipsis.
    """
    text = " ".join((line or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    # Only honour the word boundary if it is not so early that the caption
    # becomes a fragment; a single very long token is better shown clipped.
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:.\u2014-") + "\u2026"


def _media_file(asset: str) -> Any:
    rel = asset[len("asset://") :]
    path = (_MEDIA_ROOT / rel).resolve()
    try:
        path.relative_to(_MEDIA_ROOT)
    except ValueError:
        return None
    return path if path.is_file() else None


# ---------------------------------------------------------- show_exercise
#
# `kind` is exactly {choice, vocabulary, roleplay}. matching, sentence_builder,
# pronunciation and explore are rejected by design -- see
# docs/decisions/2026-08-18-show-exercise-tool.md. Core validates structure
# only: option count, duplicate ids, correct_id membership, string length and
# the same evaluative/HTML/URL ban `write_board` already uses. Never whether
# the answer is pedagogically right (tests/test_no_unit_pedagogy.py).

_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$", re.IGNORECASE)
_ITEM_TEXT_MAX = 60
EXERCISE_KINDS = frozenset({"choice", "vocabulary", "roleplay"})


def _clean_slug(raw: Any) -> str | None:
    text = str(raw or "").strip()
    if not _SLUG.match(text):
        return None
    return text


def _clean_media_item(raw: Any, *, label: str) -> tuple[dict[str, Any] | None, str | None]:
    """Validate the ``{id, text?, asset?}`` shape shared by option/item lists."""
    if not isinstance(raw, dict):
        return None, f"{label} must be an object"
    item_id = _clean_slug(raw.get("id"))
    if item_id is None:
        return None, f"{label}.id must be a short unique slug"
    out: dict[str, Any] = {"id": item_id}
    raw_text = raw.get("text")
    if raw_text is not None:
        reason = _check_free_text(
            str(raw_text), min_len=1, max_len=_ITEM_TEXT_MAX, label=f"{label}.text"
        )
        if reason:
            return None, reason
        out["text"] = " ".join(str(raw_text).split())
    raw_asset = raw.get("asset")
    if raw_asset is not None:
        asset = _as_asset(str(raw_asset))
        if asset is None or _media_file(asset) is None:
            return None, f"{label}.asset must be a real asset:// id"
        out["asset"] = asset
    if "text" not in out and "asset" not in out:
        return None, f"{label} needs text or asset"
    return out, None


def _clean_item_list(
    raw: Any, *, min_n: int, max_n: int, label: str
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not isinstance(raw, list) or not (min_n <= len(raw) <= max_n):
        return None, f"{label} must be a list of {min_n}..{max_n}"
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw:
        item, reason = _clean_media_item(entry, label=label[:-1] if label.endswith("s") else label)
        if reason:
            return None, reason
        if item["id"] in seen:
            return None, f"duplicate {label} id"
        seen.add(item["id"])
        items.append(item)
    return items, None


def _validate_choice(content: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    reason = _check_free_text(str(content.get("prompt") or ""), min_len=1, max_len=140, label="prompt")
    if reason:
        return None, None, reason
    prompt = " ".join(str(content.get("prompt")).split())
    options, reason = _clean_item_list(content.get("options"), min_n=2, max_n=4, label="options")
    if reason:
        return None, None, reason
    option_ids = {option["id"] for option in options}
    correct_id = str(content.get("correct_id") or "")
    if correct_id not in option_ids:
        # Name the legal ids. A refusal she cannot act on costs her the whole
        # move: observed live, she reached for show_exercise, was told only
        # that correct_id was wrong, and fell back to talking instead of
        # putting the check up.
        legal = ", ".join(sorted(option_ids))
        return None, None, (
            f"correct_id {correct_id!r} is not one of the option ids you sent "
            f"({legal}) -- resend with correct_id set to one of those"
        )
    stored = {"prompt": prompt, "options": options, "correct_id": correct_id}
    revealed = {"correctId": correct_id} if content.get("reveal") is True else None
    return stored, revealed, None


def _validate_vocabulary(content: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    items, reason = _clean_item_list(content.get("items"), min_n=2, max_n=8, label="items")
    if reason:
        return None, reason
    stored: dict[str, Any] = {"items": items, "interaction": "none"}
    raw_highlight = content.get("highlight_id")
    if raw_highlight is not None:
        highlight_id = str(raw_highlight)
        if highlight_id not in {item["id"] for item in items}:
            return None, "highlight_id must match an item id"
        stored["highlight_id"] = highlight_id
    return stored, None


def _validate_roleplay(content: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    stored: dict[str, Any] = {}
    for key in ("environment", "ai_role", "student_role"):
        raw = content.get(key)
        reason = _check_free_text(str(raw or ""), min_len=1, max_len=40, label=key)
        if reason:
            return None, reason
        stored[key] = " ".join(str(raw).split())
    raw_phrases = content.get("target_phrases")
    if not isinstance(raw_phrases, list) or not (1 <= len(raw_phrases) <= 5):
        return None, "target_phrases must be a list of 1..5 strings"
    phrases: list[str] = []
    for raw_phrase in raw_phrases:
        reason = _check_free_text(str(raw_phrase or ""), min_len=1, max_len=80, label="target_phrases")
        if reason:
            return None, reason
        phrases.append(" ".join(str(raw_phrase).split()))
    stored["target_phrases"] = phrases
    return stored, None


@dataclass
class TeacherOS:
    core: Any
    unit_id: str
    learner_id: str
    last_say: str | None = None
    last_present: dict[str, Any] | None = None
    last_writing: str | None = None
    last_images: dict[str, str] = field(default_factory=dict)
    last_clip: dict[str, str] | None = None
    last_exercise: dict[str, Any] | None = None
    evidence: list[dict[str, str]] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    # Her own plan for this period, mirrored from SQL so a turn never waits on
    # a read. Nothing in this file may branch on its content.
    plan: str = ""
    # Per-turn census, reset at every turn. Names and counts only -- never a
    # teacher line, never a child's words. This is the six-month tell: an E4B
    # that quietly stops bundling, or stops touching the board and talks all
    # period, looks exactly like a working teacher in any single transcript.
    turn_tools: list[str] = field(default_factory=list)
    turn_refusals: list[str] = field(default_factory=list)
    turn_board_skips: list[str] = field(default_factory=list)
    turn_chalked: bool = False
    # Moves she has made since anyone last answered her. Reset by a child
    # speaking, incremented by each say she gets out.
    moves_since_reply: int = 0
    # She has handed the room to the adult and is waiting. The period is NOT
    # closed -- it is paused, and only a person ends it.
    escalated: bool = False
    # WHICH file, WHICH track, WHICH picture -- not just how many tools. Tool
    # names alone could not answer the first question the failing lesson raised:
    # did she open keys.md before judging, or never open it at all?
    turn_reads: list[str] = field(default_factory=list)
    turn_clips: list[str] = field(default_factory=list)
    turn_images: list[str] = field(default_factory=list)
    turn_exercises: list[str] = field(default_factory=list)
    turn_evidence: list[str] = field(default_factory=list)
    # The same, accumulated over the whole period. A lesson is the unit that
    # succeeds or fails; a turn is not. "No clip played all period" is the
    # finding, and no single turn can show it.
    period_reads: list[str] = field(default_factory=list)
    period_clips: list[str] = field(default_factory=list)
    period_images: list[str] = field(default_factory=list)
    period_exercises: list[str] = field(default_factory=list)
    period_evidence: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    last_say_at: float | None = None
    awaiting_answer: bool = False
    nudged_once: bool = False
    # When she asked the room to hand her the next beat of a drill or a clip.
    wake_at: float | None = None
    last_student_at: float | None = None
    last_heartbeat_at: float | None = None
    turn_kind: str | None = None
    # What Core witnessed on THIS turn: which turn it is, and whether a child
    # actually produced anything. Evidence is anchored to both -- she is
    # stateless per turn, so a row written on a turn with no student act is
    # necessarily about an utterance that did not happen.
    turn_id: str | None = None
    turn_student_text: str = ""
    # Objectives already recorded on this turn. The unique index on
    # (session_id, response_turn_id, skill) could never fire while
    # response_turn_id was a fresh random uuid on every call.
    turn_recorded: set[str] = field(default_factory=set)
    # Counts only, for the census: how often she looked into the record.
    turn_recalls: int = 0
    turn_language: str | None = None

    def map_path(self) -> str:
        return f"units/{self.unit_id}/map.md"

    def close_period(self) -> None:
        """End the period: close the row, drop the OS, mark the clock."""
        # Before the OS is dropped -- it holds the only copy of what the period
        # actually used, and a period that played no clip and marked everything
        # correct is invisible in any single turn's line.
        _log_period_census(self)
        core = self.core
        db = getattr(core, "db", None)
        ender = getattr(db, "end_session", None)
        session_id = getattr(core, "session_id", None)
        if callable(ender) and session_id:
            try:
                ender(session_id)
            except Exception:  # noqa: BLE001 -- the room outlives the bookkeeping
                pass
        core.last_close_at = time.time()
        core.teacher_os = None

    def catalog(self) -> dict[str, list[str]]:
        return unit_catalog(self.unit_id)

    def _exercise_scene(self, store: Any) -> Any:
        """Render `last_exercise` as the already-wired choice/vocabulary/roleplay scene.

        Core never accepts or emits `chosenId` -- it is not in the show_exercise
        schema, so it cannot reach this method. The mint tick on the correct
        option is the only verdict the board ever shows.
        """
        ex = self.last_exercise or {}
        kind = ex.get("kind")
        content = ex.get("content") or {}
        if kind == "choice":
            props: dict[str, Any] = {"prompt": content["prompt"], "options": content["options"]}
            if ex.get("revealed"):
                props["revealed"] = {"correctId": ex["revealed"]["correctId"]}
            return store.set_scene("choice", props)
        if kind == "vocabulary":
            props = {"items": content["items"], "interaction": "none"}
            if "highlight_id" in content:
                props["highlightId"] = content["highlight_id"]
            return store.set_scene("vocabulary", props)
        # roleplay
        props = {
            "environment": content["environment"],
            "aiRole": content["ai_role"],
            "studentRole": content["student_role"],
            "targetPhrases": content["target_phrases"],
        }
        return store.set_scene("roleplay", props)

    def _mark_board(self, source: str) -> None:
        """Remember which hand touched the board last."""
        self.last_board_source = source

    def _push_stage(self) -> None:
        """Projector board: legal scene.update, not the invalid board.present.

        The most recent hand wins. `last_exercise` / `last_images` /
        `last_writing` all persist across turns so `read_board` can report
        them, so a fixed ranking would let a picture shown five minutes ago
        beat writing she just chalked up -- her writing would simply never
        appear. Rank by what she touched last instead.
        """
        store = getattr(self.core, "store", None)
        bus = getattr(self.core, "bus", None)
        if store is None or bus is None:
            return
        caption = _caption_for_board(self.last_say)
        source = getattr(self, "last_board_source", None)
        order = [
            ("exercise", bool(self.last_exercise)),
            ("images", bool(self.last_images)),
            ("writing", bool(self.last_writing)),
        ]
        available = [name for name, present in order if present]
        if not available:
            return
        chosen = source if source in available else available[0]

        if chosen == "exercise":
            scene = self._exercise_scene(store)
        elif chosen == "images":
            if len(self.last_images) > 1:
                # A two-asset show_image has no single-asset ImageProps shape
                # on the wire. Route the pair through the already-wired
                # vocabulary scene instead of inventing a new component.
                items = [
                    {"id": "left", "asset": self.last_images.get("left", "")},
                    {"id": "right", "asset": self.last_images.get("right", "")},
                ]
                scene = store.set_scene("vocabulary", {"items": items, "interaction": "none"})
            else:
                asset = self.last_images.get("main") or next(iter(self.last_images.values()))
                scene = store.set_scene("image", {"asset": asset, "caption": caption})
        else:
            scene = store.set_scene("text", {"text": self.last_writing})
        bus.publish("scene.update", scene)

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        """Run one tool and count it. The census is the only thing added here."""
        result = await self._dispatch(name, arguments)
        self.turn_tools.append(name)
        if isinstance(result, dict):
            if result.get("ok") is False:
                self.turn_refusals.append(
                    name + ":" + _reason_class(str(result.get("reason") or ""))
                )
            else:
                self._note_use(name, arguments, result)
            board = str(result.get("board") or "")
            if board == "applied":
                self.turn_chalked = True
            elif board.startswith("skipped:"):
                self.turn_board_skips.append(_reason_class(board))
        return result

    def _note_use(self, name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        """Which material a successful call actually reached for.

        Only what she used, and only as short names -- a path, a track id, an
        objective. No teacher line, no child's words, no learner id.
        """

        def add(turn: list[str], period: list[str], value: str, *, tally: bool = False) -> None:
            """`tally=True` keeps repeats. Everything else is a set of what was touched.

            Reads, clips, images and exercises answer "did she ever use this",
            so collapsing repeats is right. Evidence answers "how many times has
            the class tried this", and collapsing repeats there destroys the
            only number the unit map's pacing law is written against -- "Time is
            not the measure; attempts are".

            Measured 2026-08-20: ten consecutive `answer-wellbeing wrong` rows
            in SQL rendered as `THIS_PERIOD=answer-wellbeing x2`, and the period
            census reported `outcomes {correct: 1, near: 1, wrong: 1}` for a
            period in which the child got it wrong ten times. Both instruments
            said the marking was healthy. `turn_recorded` already caps this at
            one row per objective per turn, so keeping repeats cannot run away.
            """
            value = value.strip()
            if not value:
                return
            turn.append(value)
            if tally or value not in period:
                period.append(value)

        if name == "read_library":
            add(self.turn_reads, self.period_reads, str(result.get("path") or ""))
        elif name == "search_library":
            for hit in result.get("hits") or []:
                add(self.turn_reads, self.period_reads, str((hit or {}).get("path") or ""))
        elif name == "play_clip":
            add(self.turn_clips, self.period_clips, _asset_name(arguments.get("asset")))
        elif name == "show_image":
            add(self.turn_images, self.period_images, _asset_name(arguments.get("asset")))
            add(self.turn_images, self.period_images, _asset_name(arguments.get("second")))
        elif name == "show_exercise":
            add(self.turn_exercises, self.period_exercises, str(arguments.get("kind") or ""))
        elif name == "record_evidence":
            add(
                self.turn_evidence,
                self.period_evidence,
                ":".join(
                    (
                        str(arguments.get("objective_id") or "?"),
                        str(arguments.get("outcome") or "?"),
                        str(arguments.get("mode") or "-"),
                    )
                ),
                tally=True,
            )

    async def _dispatch(self, name: str, arguments: dict[str, Any]) -> Any:
        if self.turn_kind == "prepare" and name not in PREPARE_TOOLS:
            return {
                "ok": False,
                "reason": (
                    "there is no class yet -- before the room fills you may only "
                    "read the library and write your plan"
                ),
            }

        if name == "read_library":
            try:
                got = read_library(str(arguments.get("path") or ""))
            except LibraryError as exc:
                return {"ok": False, "reason": str(exc)}
            self.reads.append(got["path"])
            return {"ok": True, **got}

        if name == "recall_student":
            # Scoped to THIS learner in Core, never by an argument: the id is
            # not hers to supply. Same shape as record_evidence refusing a
            # student_id that is not the learner in the room.
            recall = getattr(getattr(self.core, "db", None), "recall", None)
            if not callable(recall):
                return {"ok": False, "reason": "this room keeps no learner record"}
            query = " ".join(str(arguments.get("query") or "").split())
            if len(query) < 2:
                return {"ok": False, "reason": "recall_student needs something to look for"}
            raw_limit = arguments.get("limit")
            limit = raw_limit if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) else 5
            try:
                found = recall(query, max(1, min(int(limit), 8)), student_id=self.learner_id)
            except Exception as exc:  # noqa: BLE001 -- a lookup must not cost the turn
                log.warning("recall_student failed (%s)", exc)
                return {"ok": False, "reason": "the record could not be read"}
            # Empty is a normal answer, not a failure: a child on their first
            # day has no past and she has to teach them anyway. Saying ok=False
            # would read as "something broke" and invite a retry.
            notes = [
                {"when": getattr(item, "when", ""), "text": getattr(item, "text", "")}
                for item in found
            ]
            self.turn_recalls += len(notes)
            return {"ok": True, "notes": notes, "found": len(notes)}

        if name == "search_library":
            try:
                got = search_library(str(arguments.get("query") or ""))
            except LibraryError as exc:
                return {"ok": False, "reason": str(exc)}
            for hit in got["hits"]:
                path = str(hit.get("path") or "")
                if path:
                    self.reads.append(path)
            return {"ok": True, **got}

        if name == "write_board":
            raw_text = str(arguments.get("text") or "")
            text = _clean_board_markdown(raw_text)
            if not text:
                return {"ok": False, "reason": _board_refusal(raw_text, "board markdown")}
            self.last_writing = text
            self.last_present = {"layout": "text", "slots": {"main": text}}
            self._mark_board("writing")
            self._push_stage()
            return {"ok": True, "applied": True}

        if name == "read_board":
            return {
                "ok": True,
                "writing": self.last_writing,
                "images": dict(self.last_images),
                "clip": self.last_clip,
                "exercise": dict(self.last_exercise) if self.last_exercise else None,
            }

        if name == "show_exercise":
            kind = str(arguments.get("kind") or "")
            if kind not in EXERCISE_KINDS:
                return {"ok": False, "reason": "kind must be choice, vocabulary, or roleplay"}
            # The wire is FLAT (see mcp_server: an untyped nested object came
            # back empty from the provider every time). A nested `content` is
            # still accepted, because that is how the older tests and any
            # in-process caller spell it, and because refusing a shape that
            # carries the same information would be pedantry a child pays for.
            content = arguments.get("content")
            if not isinstance(content, dict) or not content:
                content = {
                    key: arguments[key]
                    for key in (
                        "prompt", "options", "correct_id", "items",
                        "environment", "ai_role", "student_role",
                        "target_phrases", "reveal",
                    )
                    if key in arguments
                }
            if not content:
                return {
                    "ok": False,
                    "reason": f"{kind} needs its fields -- see the tool description",
                }
            if kind == "choice":
                stored, revealed, reason = _validate_choice(content)
            elif kind == "vocabulary":
                stored, reason = _validate_vocabulary(content)
                revealed = None
            else:
                stored, reason = _validate_roleplay(content)
                revealed = None
            if reason or stored is None:
                return {"ok": False, "reason": reason or "invalid exercise content"}
            self.last_exercise = {"kind": kind, "content": stored, "revealed": revealed}
            self._mark_board("exercise")
            self._push_stage()
            return {"ok": True, "applied": True}

        if name == "show_image":
            # `asset` (+ optional `second`) is the whole calling convention.
            # It used to also answer to left/right, which was a second, invisible
            # spelling of the same argument -- a coin flip a 4B model paid for
            # every turn, and the reason show_image({turn_id}) was schema-legal.
            left = _as_asset(str(arguments.get("asset") or ""))
            right = _as_asset(str(arguments.get("second") or ""))
            if left is None:
                return {"ok": False, "reason": "show_image needs an asset:// id"}
            if _media_file(left) is None:
                return {"ok": False, "reason": "image asset not found"}
            if right:
                if _media_file(right) is None:
                    return {"ok": False, "reason": "image asset not found"}
                self.last_images = {"left": left, "right": right}
                self.last_present = {"layout": "two_cards", "slots": dict(self.last_images)}
            else:
                self.last_images = {"main": left}
                self.last_present = {"layout": "image", "slots": dict(self.last_images)}
            self._mark_board("images")
            self._push_stage()
            return {"ok": True, "applied": True}

        if name == "play_clip":
            asset = _as_asset(str(arguments.get("asset") or ""))
            if asset is None:
                return {"ok": False, "reason": "play_clip needs an asset:// id"}
            if _media_file(asset) is None:
                return {"ok": False, "reason": "clip asset not found"}
            transcript = " ".join(str(arguments.get("transcript") or "").split())[:200]
            self.last_clip = {"asset": asset, "transcript": transcript}
            publish = getattr(self.core, "publish_speech", None)
            if callable(publish):
                publish(transcript or " ", source="clip", audio_asset=asset)
            return {"ok": True, "applied": True}

        if name == "say":
            line = " ".join(str(arguments.get("teacher_line") or "").split())
            if _is_heartbeat_ok(line):
                return {"ok": True, "applied": False, "silent": True}
            reason = _check_teacher_line(line)
            if reason:
                return {"ok": False, "reason": reason}
            # Speaking and chalking are ONE physical act -- she writes while she
            # talks -- so they belong in one call. Everything else she can do
            # (a picture, a clip, an exercise) is a different act and stays a
            # different tool: if one of those is malformed, she can still speak
            # and the lesson limps forward. A merged tool was tried on
            # 2026-08-19 and failed exactly there: one bad sub-field killed the
            # speech too, and a strong model then repeated the call until the
            # circuit breaker took the room out. In an unattended classroom that
            # is a teacher standing silent in front of children.
            #
            # The chalk rides on say only because it DEGRADES: bad markdown is
            # skipped and the class still hears her. But skipping silently was
            # its own bug -- she believed she had written, and the next turn's
            # WRITING= said otherwise. Degrade loudly, fail never: the result
            # names what happened to the board while `ok` stays True.
            raw_board = str(arguments.get("board_text") or "")
            board_text = _clean_board_markdown(raw_board) if raw_board else None
            # A DELIBERATE HAND BEATS THE CONVENIENCE ONE. show_exercise,
            # show_image and write_board are whole tools she chose to call;
            # board_text rides along on say. When both land in the same message
            # the chalk used to win by arriving last, and it silently threw the
            # other one away.
            #
            # That is not hypothetical and it is our own doing: the standing
            # prompt says "Put every tool call you already know you need in ONE
            # message -- including say". Recorded live 2026-08-20, she called
            # show_exercise(choice) and said "Look at the board. How does Mai
            # answer? A or B?" in one message -- and the board showed her
            # board_text instead, so the class was asked to choose between
            # options it could not see. The same standing prompt warns about
            # exactly that outcome two paragraphs further down.
            #
            # Degrade loudly, as the rest of this branch already does: the line
            # is spoken, the board keeps what she deliberately put there, and
            # the result says why so the next turn is not a guess.
            if board_text and any(tool in BOARD_TOOLS for tool in self.turn_tools):
                board_result = (
                    "skipped: the board already shows what you put up this turn -- "
                    "board_text would have replaced it"
                )
            elif board_text:
                board_result = "applied"
                self.last_writing = board_text
                self.last_present = {"layout": "text", "slots": {"main": board_text}}
                self._mark_board("writing")
                self._push_stage()
            elif raw_board:
                board_result = "skipped: " + _board_refusal(raw_board, "board_text")
            else:
                board_result = "none"

            self.last_say = line
            self.last_say_at = time.time()
            self.moves_since_reply += 1
            # She tells us whether she just asked something. Core does not
            # guess it from a question mark -- "Now you try" expects an answer
            # and carries no "?", while "How are you?" modelled aloud does not.
            # The nudge budget belongs to the QUESTION, not to the sentence.
            # Resetting it on every say meant it could never accumulate: she
            # asked, the nudge fired, she spoke on that nudge turn, the counter
            # went back to zero, and the room called it "they are thinking"
            # forever. Measured 2026-08-19 -- a whole period of nothing but
            # heartbeats, one line each. Reset it only when she asks something
            # NEW.
            asking = bool(arguments.get("awaiting_answer"))
            if asking and not self.awaiting_answer:
                self.nudged_once = False
            self.awaiting_answer = asking
            # A plain say no longer cancels a pending beat. It used to, so the
            # first time she answered a child who interrupted a drill, the drill
            # silently ended. Only an explicit wake_in_s=0 clears it.
            wake_in = arguments.get("wake_in_s")
            if isinstance(wake_in, (int, float)) and not isinstance(wake_in, bool):
                if wake_in > 0:
                    self.wake_at = time.time() + min(
                        max(float(wake_in), WAKE_MIN_S), WAKE_MAX_S
                    )
                else:
                    self.wake_at = None
            publish = getattr(self.core, "publish_speech", None)
            if callable(publish):
                publish(line, source="agent")
            closing = bool(arguments.get("closing"))
            if closing and not any(
                r.endswith("skills/close-a-period/SKILL.md") for r in self.reads
            ):
                # Ending a period is a professional act with a procedure, and on
                # 2026-08-19 she ended one after fifteen minutes and eight
                # exchanges without ever opening it. Core reads not a word of
                # the skill -- it enforces only that the procedure was opened,
                # exactly as it names keys.md before she judges.
                #
                # She is NOT silenced for it: the line is spoken, the period
                # stays open, and the result says why. Degrade loudly, fail
                # never -- a refused `say` is a teacher standing mute.
                closing = False
                board_result = (
                    board_result + "; " if board_result != "none" else ""
                ) + "not closed: read skills/close-a-period/SKILL.md first"
            if closing:
                # She said goodbye, so the period is over. A teacher ends the
                # lesson; she does not run until someone stops her. Closing
                # after the line is spoken, not before, so the room hears it.
                self.close_period()
            return {"ok": True, "applied": True, "board": board_result}

        if name == "plan":
            # She keeps her own intention. Core STORES it and hands it back;
            # Core never branches on a word of it. The moment anything here
            # reads the plan to decide something, the teacher is a cassette
            # again and NS-1 is gone.
            text = " ".join(str(arguments.get("plan") or "").split())
            reason = _check_free_text(
                text, min_len=1, max_len=PLAN_MAX_CHARS, label="plan"
            )
            if reason:
                return {"ok": False, "reason": reason}
            db = getattr(self.core, "db", None)
            saver = getattr(db, "save_lesson_plan", None)
            session_id = str(getattr(self.core, "session_id", "") or "")
            if not callable(saver) or not session_id:
                return {"ok": False, "reason": "no open session to plan for"}
            revision = saver(session_id, self.unit_id, text)
            self.plan = text
            return {"ok": True, "applied": True, "revision": revision}

        if name == "call_the_adult":
            reason = str(arguments.get("reason") or "").strip()
            if reason not in ESCALATION_REASONS:
                return {"ok": False, "reason": "reason must be one of " + ", ".join(sorted(ESCALATION_REASONS))}
            detail = " ".join(str(arguments.get("detail") or "").split())[:200]
            # The same free-text rules as everything else she writes -- an
            # escalation is read by a person, and a URL or a grade word has no
            # business in one either.
            if detail:
                bad = _check_free_text(detail, min_len=1, max_len=200, label="detail")
                if bad:
                    return {"ok": False, "reason": bad}
            core = self.core
            core.escalation = {
                "reason": reason,
                "detail": detail,
                "unitId": self.unit_id,
                "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            # She stops. NOT a period close: closing writes an ended session and
            # counts as a period held, and a lesson abandoned to the adult is
            # not a period this class has had. The room stays exactly as it is
            # -- board, picture, session -- so the adult walks into what the
            # children were looking at, and so the period can be resumed.
            self.escalated = True
            log.warning("teacher escalation reason=%s unit=%s", reason, self.unit_id)
            return {"ok": True, "applied": True}

        if name == "record_evidence":
            # Core is a WITNESS, not a marker. Every refusal below is a fact
            # Core saw with its own eyes -- no turn happened, the child said
            # nothing, this row is already written. Whether the answer was good
            # enough is hers, and stays hers: see
            # docs/decisions/2026-08-19-core-is-a-witness.md.
            if self.turn_kind is not None:
                return {
                    "ok": False,
                    "reason": f"{self.turn_kind} is not student evidence",
                }
            if not self.turn_student_text.strip():
                return {
                    "ok": False,
                    "reason": "no child spoke this turn -- there is nothing to record",
                }
            # Unattributed evidence is refused in code, not merely discouraged
            # in a prompt (docs/decisions/2026-08-18-show-exercise-tool.md).
            # No row is written for a missing, placeholder, or wrong-learner id.
            student_id = str(arguments.get("student_id") or "").strip()
            if not student_id or student_id.casefold() in PLACEHOLDER_STUDENT_IDS:
                return {
                    "ok": False,
                    "reason": "record_evidence needs a real student_id, not a class-wide placeholder",
                }
            if student_id != self.learner_id:
                return {"ok": False, "reason": "student_id does not match the learner in this room"}
            objective = str(arguments.get("objective_id") or "").strip()
            outcome = str(arguments.get("outcome") or "").strip()
            raw_mode = arguments.get("mode")
            mode = str(raw_mode or "").strip()
            if not objective or outcome not in OUTCOMES:
                return {"ok": False, "reason": "objective_id and legal outcome required"}
            if mode == "off-topic":
                return {"ok": False, "reason": "off-topic is not evidence"}
            if not mode:
                # A modeless row silently fell out of SKILL_CARD coverage
                # (ATTEMPT_MODES is {name, point}), so evidence she recorded
                # evaporated from the one thing that reads it.
                return {"ok": False, "reason": "mode is required: name, point, or ask"}
            if mode not in MODES:
                return {"ok": False, "reason": "mode must be name, point, or ask"}
            # Fail CLOSED. An empty catalog means the unit folder is missing or
            # unreadable -- not that every objective is suddenly legal. The old
            # `if allowed and ...` guard silently accepted invented ids the
            # moment a unit was renamed.
            allowed = self.catalog()["objectives"]
            if not allowed:
                return {"ok": False, "reason": f"unit {self.unit_id} has no objectives on disk"}
            if objective not in allowed:
                return {"ok": False, "reason": "objective_id is not on the unit map"}
            # One row per objective per turn. NOT per session: a child who was
            # `wrong` at minute 10 and `correct` after scaffolding at minute 30
            # is the most valuable pattern this memory can hold -- wrong-then-
            # right IS the learning -- and a session key would destroy it.
            if objective in self.turn_recorded:
                return {
                    "ok": False,
                    "reason": f"already recorded {objective} this turn",
                }
            stored_mode = mode or None
            note = f"unit={self.unit_id}; outcome={outcome}"
            if stored_mode:
                note += f"; mode={stored_mode}"
            row = {
                "objective_id": objective[:128],
                "outcome": outcome,
                "unit_id": self.unit_id,
                "mode": stored_mode or "",
            }
            self.evidence.append(row)
            self.turn_recorded.add(objective)
            db = getattr(self.core, "db", None)
            record = getattr(db, "record_observation", None)
            if callable(record):
                payload = dict(
                    session_id=getattr(self.core, "session_id", None),
                    # The REAL turn. This used to be a fresh random uuid on
                    # every call, which meant the unique index on
                    # (session_id, response_turn_id, skill) could never fire
                    # once, and no row could ever be traced back to the
                    # utterance it claims to be about.
                    response_turn_id=self.turn_id or f"ev-{uuid.uuid4().hex[:12]}",
                    activity_id=self.unit_id,
                    mode=stored_mode,
                )
                try:
                    record(student_id, objective[:128], outcome, note, **payload)
                except TypeError:
                    payload.pop("mode", None)
                    record(student_id, objective[:128], outcome, note, **payload)
            return {"ok": True, "applied": True}

        return {"ok": False, "reason": f"unknown tool {name}"}


def _teacher_session_summary(rows: list[dict[str, Any]], unit_id: str) -> dict[str, Any]:
    named: list[str] = []
    pointed: list[str] = []
    missed: list[str] = []
    for row in rows:
        skill = str(row.get("skill") or "").strip()
        if not skill:
            continue
        mode = str(row.get("mode") or "").strip()
        result = str(row.get("result") or "").strip()
        if mode == "name" and result == "correct":
            named.append(skill)
        elif mode == "point" and result == "correct":
            pointed.append(skill)
        elif result in {"wrong", "uncertain"}:
            missed.append(skill)
    named = list(dict.fromkeys(named))
    pointed = list(dict.fromkeys(pointed))
    missed = list(dict.fromkeys(missed))
    bits = [f"{len(rows)} observation(s) on {unit_id}."]
    if named:
        bits.append("Named: " + ", ".join(named) + ".")
    if pointed:
        bits.append("Pointed: " + ", ".join(pointed) + ".")
    if missed:
        bits.append("Unsure: " + ", ".join(missed) + ".")
    return {
        "summary": " ".join(bits),
        "weakPoints": missed[:3],
        "nextFocus": missed[:3] or pointed[:3] or named[:3],
    }


def _close_open_teacher_sessions(db: Any, *, learner_id: str, unit_id: str) -> None:
    opener = getattr(db, "list_open_sessions", None)
    ender = getattr(db, "end_session", None)
    writer = getattr(db, "write_session_summary", None)
    lister = getattr(db, "list_observations", None)
    if not callable(opener) or not callable(ender):
        return
    for session in opener(learner_id) or []:
        session_id = str(session.get("id") or "")
        if not session_id:
            continue
        if callable(writer) and callable(lister):
            blurb = _teacher_session_summary(
                lister(session_id=session_id),
                str(session.get("lesson_id") or unit_id),
            )
            writer(
                session_id,
                blurb["summary"],
                blurb["weakPoints"],
                blurb["nextFocus"],
            )
        ender(session_id)


# After she closes, the room must not immediately open another period. The
# Stage still holds the audio lease and the pulse still ticks, so without this
# she would say goodbye and greet the same class three seconds later, forever.
# A real next period is a timetable event, and Bright has no day clock yet.
#
# Overridable because ten minutes is right for a school and wrong for anyone
# rehearsing. The failure it causes is silent and looks exactly like a broken
# room: she closes a period, someone opens the front door again, and NOTHING
# HAPPENS -- no error, no log line anyone would notice, for ten minutes. That
# is a lost take, or a lost afternoon of testing. The default is unchanged.
REOPEN_AFTER_CLOSE_S = float(os.environ.get("BRIGHT_REOPEN_AFTER_CLOSE_S", "600"))


def resume_teacher_session(core: Any) -> TeacherOS | None:
    """Re-attach to a period that was interrupted, instead of starting a new one.

    "Restart the teacher, never the lesson." A child watching the screen should
    not be able to tell that anything happened; greeting the class a second time
    is the tell that this is a machine.

    What survives is what lives in the database: which unit, which learner, and
    every observation already recorded -- so SKILL_CARD and PAST come back
    intact and she continues from what they actually did -- and, since 2026-08-19,
    the plan she wrote for this period, which is exactly the thing a restart
    used to destroy. What does not survive is the board. She is told to look up,
    not to open a class, so she reorients rather than re-greets.
    """
    db = getattr(core, "db", None)
    finder = getattr(db, "find_open_session", None)
    if not callable(finder):
        return None
    row = finder()
    if not row:
        return None
    unit_id = str(row.get("lesson_id") or "")
    learner_id = str(row.get("student_id") or "")
    if not unit_id or not learner_id:
        return None
    core.student_id = learner_id
    core.session_id = row["id"]
    core.teacher_os = TeacherOS(core, unit_id=unit_id, learner_id=learner_id)
    getter = getattr(db, "get_lesson_plan", None)
    if callable(getter):
        stored = getter(core.session_id) or {}
        core.teacher_os.plan = str(stored.get("plan") or "")
    return core.teacher_os


PREPARE_SESSION_PREFIX = "prepare:"


def prepared_plan_id(unit_id: str) -> str:
    """Where a plan written before class waits for the class to arrive."""
    return PREPARE_SESSION_PREFIX + unit_id


async def prepare_period(core: Any, *, unit_id: str) -> dict[str, Any]:
    """Read the unit properly, look at what this class actually struggled with,
    and draft the period -- while nobody is waiting.

    This is the only place an offline 4B model is allowed to be slow, and
    therefore the only place it is allowed to be thorough. NORTH-STAR §2's
    BEFORE box was empty because nothing ran here.

    It does NOT use the harness's own cron or child agents. Two reasons, both
    checked in the upstream source on 2026-08-19 rather than assumed:

    * `bright_live` -- the profile that pins the terminal tool and the system
      prompt -- is installed once per gateway process and applies to every
      request on it, so preparation cannot share the classroom gateway.
    * A platform whose `platform_toolsets` entry names no MCP server gets EVERY
      globally-enabled MCP server unioned in (hermes_cli/tools_config.py:2495).
      A cron job configured with `[cronjob, delegation]` would therefore be
      handed `bright-classroom` -- and `say` with it. Nothing upstream blocks
      an MCP tool by name for a child agent or a scheduled job.

    Core's own day clock has none of that, and Core is the sole state writer
    anyway (NS-1). The guarantee that preparation cannot speak lives in
    `execute`, in this file, where it is a test rather than a config option.
    """
    if getattr(core, "teacher_os", None) is not None:
        return {"ok": False, "error": "a class is in progress"}
    async with _TURN_LOCK:
        prior_session = getattr(core, "session_id", None)
        prior_student = getattr(core, "student_id", None)
        # NS-7: a child's id is a property of the deployment, not the code.
        learner_id = str(
            prior_student
            or getattr(getattr(core, "settings", None), "default_learner_id", "")
            or "learner"
        )
        # The MCP turn registry binds each turn to (session, learner) and
        # refuses a tool whose scope has drifted -- which is exactly the check
        # that should stay strict during a live class. Preparation therefore
        # declares its scope rather than being exempted from the check.
        core.session_id = prepared_plan_id(unit_id)
        core.student_id = learner_id
        core.teacher_os = TeacherOS(core, unit_id=unit_id, learner_id=learner_id)
        try:
            got = await _handle_teacher_turn(core, "[prepare]")
        finally:
            core.teacher_os = None
            core.session_id = prior_session
            core.student_id = prior_student

    # Judge preparation by what it LEFT BEHIND, not by whether she spoke.
    #
    # The harness's terminal contract requires a successful `say` to call a
    # turn complete (hermes.py: "teacher agent did not say") -- and `say` is
    # precisely what PREPARE_TOOLS forbids, because the Stage is the only
    # loudspeaker and nobody is in the room. So every preparation that did its
    # job correctly reported itself as a failure, the nightly job has been
    # failing silently since it was written, and `lastPrepare.ok` was never
    # once true. Nothing downstream noticed, because nothing read it.
    #
    # What preparation is FOR is a plan. If one is on disk, it worked.
    drafted = ""
    getter = getattr(core.db, "get_lesson_plan", None)
    if callable(getter):
        drafted = str((getter(prepared_plan_id(unit_id)) or {}).get("plan") or "")
    if drafted:
        return {"ok": True, "unitId": unit_id, "planChars": len(drafted)}
    return {
        "ok": False,
        "unitId": unit_id,
        "error": got.get("error") or "she drafted no plan",
    }


def start_teacher_session(core: Any, *, unit_id: str, learner_id: str, learner_name: str) -> TeacherOS:
    core.db.upsert_student(learner_id, learner_name, learner_name)
    _close_open_teacher_sessions(core.db, learner_id=learner_id, unit_id=unit_id)
    core.student_id = learner_id
    core.session_id = core.db.start_session(
        student_id=learner_id, lesson_id=unit_id, mode=str(core.store.mode)
    )
    core.teacher_os = TeacherOS(core, unit_id=unit_id, learner_id=learner_id)
    # A period prepared last night starts with the plan she drafted then, rather
    # than with a blank one she has to invent while a class watches.
    getter = getattr(core.db, "get_lesson_plan", None)
    if callable(getter):
        prepared = getter(prepared_plan_id(unit_id)) or {}
        plan = str(prepared.get("plan") or "")
        if plan:
            core.teacher_os.plan = plan
            core.db.save_lesson_plan(core.session_id, unit_id, plan)
    return core.teacher_os


def format_skill_memory(rows: list[dict[str, Any]]) -> tuple[str, str]:
    """Coverage + recency from SQL observations. No raw learner text.

    Reports how many observations *support*, *contradict*, or leave
    *no_decision* about each (skill, elicitation mode) pair -- not a
    confidence number. The deleted `_name_skill_stats` estimate saturated at
    1.0 after four attempts regardless of correctness and had no live reader:
    `SKILL_CARD` is this function, not the `skills` table. correct -> supported,
    wrong -> contradicted, uncertain|near -> no_decision.
    """
    coverage: dict[tuple[str, str], dict[str, int]] = {}
    past_bits: list[str] = []
    for row in rows:
        skill = str(row.get("skill") or "").strip()
        result = str(row.get("result") or "").strip()
        mode = str(row.get("mode") or "").strip() or "-"
        if not skill or not result:
            continue
        when = str(row.get("ts") or "")[:10]
        past_bits.append(f"{when} {skill} {mode} {result}".strip())
        if mode in ATTEMPT_MODES:
            bucket = coverage.setdefault(
                (skill, mode), {"supported": 0, "contradicted": 0, "no_decision": 0}
            )
            if result == "correct":
                bucket["supported"] += 1
            elif result == "wrong":
                bucket["contradicted"] += 1
            elif result in {"uncertain", "near"}:
                bucket["no_decision"] += 1
    past = "; ".join(past_bits[-8:])
    card = "; ".join(
        f"{skill} {mode} supported={counts['supported']} "
        f"contradicted={counts['contradicted']} no_decision={counts['no_decision']}"
        for (skill, mode), counts in coverage.items()
    )
    return card, past


# Orientation injection was built here on 2026-08-19 and REMOVED the same day,
# by measurement. The idea: hand her how-to-teach.md + skills/index.md + the
# active map instead of spending a round-trip on read_library, on the premise
# that a cached prompt prefix is nearly free.
#
# The premise is false for this provider. Measured against
# google/gemini-3.7-flash through OpenRouter, three identical 4,163-token
# requests in a row all reported `cached_tokens: 0`. So the injection cost
# ~2,400 extra tokens on EVERY call and bought back one round-trip on the
# first turn only. Turns went 41/11/14s -> 46/38/27s. Worse, measured.
#
# This is a finding about ONE provider, not a law. Revisit whenever the brain
# changes, and especially for the local endgame: llama.cpp / OVMS keep the KV
# cache for a shared prompt prefix between calls, so a stable injected block is
# genuinely near-free there -- exactly the premise that failed here. On a local
# Gemma the round-trip is also CPU we own, which makes cutting round-trips worth
# MORE, not less.
#
# The check to run before rebuilding this, whatever the provider: confirm
# `usage.prompt_tokens_details.cached_tokens` is non-zero on a repeat call (or
# that the local runtime reports a prefix-cache hit) BEFORE building on it.
def _session_recall(os_: TeacherOS) -> list[Any]:
    from bright_contracts import RecalledMemory

    notes: list[Any] = []
    # Core reports the clock; she decides what it means. How long a period runs
    # is in the unit map, which is curriculum -- Core must not know it.
    elapsed_min = int((time.time() - os_.started_at) // 60)
    notes.append(RecalledMemory(text=f"PERIOD_MINUTES={elapsed_min}", when="now"))
    # How many periods this class has already finished on this unit. Core
    # witnessed every one of them open and close, so counting them is the same
    # species of act as reading the clock. What the number MEANS -- that the
    # third meeting is "Period 3 -- Put it together" -- is in the unit map,
    # where curriculum belongs. Core must never look that up, or the map stops
    # being the thing that decides and Python starts.
    counter = getattr(getattr(os_.core, "db", None), "count_periods_held", None)
    if callable(counter):
        try:
            held = counter(student_id=os_.learner_id, lesson_id=os_.unit_id)
        except Exception:  # noqa: BLE001 -- a missing count must not cost a turn
            held = None
        if held is not None:
            notes.append(RecalledMemory(text=f"PERIODS_HELD={held}", when="now"))
    # What she has already tried THIS period, per objective. The unit map's own
    # pacing law is "Time is not the measure; attempts are", and it was
    # unexecutable because nothing counted attempts.
    # ...and HOW IT WENT, which this line used to throw away: it split on ":"
    # and kept only the objective, so "they have tried this ten times" and
    # "they have failed this ten times" rendered identically. The half of the
    # fact that would change her mind was the half Core dropped. Measured
    # 2026-08-20: ten `wrong` in a row on one objective, and she drilled the
    # same phrase for fourteen of fifteen turns.
    #
    # Core is still only counting its own rows -- whether ten wrongs mean back
    # up is hers, and `scaffold-down` is the skill that says what that looks
    # like. This value never appears inside a Core `if`.
    if os_.period_evidence:
        tally: dict[str, dict[str, int]] = {}
        for row in os_.period_evidence:
            parts = (row.split(":") + ["?", "?", "-"])[:3]
            objective, outcome = parts[0], parts[1]
            seen = tally.setdefault(objective, {})
            seen[outcome] = seen.get(outcome, 0) + 1
        entries = []
        for objective, outcomes in tally.items():
            total = sum(outcomes.values())
            detail = ", ".join(f"{name} {n}" for name, n in sorted(outcomes.items()))
            entries.append(f"{objective} x{total} ({detail})")
        notes.append(RecalledMemory(text="THIS_PERIOD=" + "; ".join(entries), when="now"))
    # How long she has been talking to nobody. Core holds both marks already;
    # this is the same species of fact as PERIOD_MINUTES.
    #
    # Without it a silent room is invisible to her: LAST_SAY is the whole of her
    # injected self-history, so every turn where nobody answers is her FIRST
    # such turn. Measured 2026-08-19, four minutes of silence: she cycled the
    # same three phrases -- "Hello. I'm Ben." / "Hello! I'm..." / "Hello, I'm..."
    # -- and then reached for close-a-period, because she had genuinely run out
    # of ideas she could remember having had.
    #
    # It is also what makes the north star's escalation trigger -- "class-wide
    # disengagement that pacing changes have not fixed" -- expressible at all.
    if os_.last_student_at:
        quiet_min = int((time.time() - os_.last_student_at) / 60)
    else:
        quiet_min = int((time.time() - os_.started_at) / 60)
    if os_.moves_since_reply >= 2:
        notes.append(
            RecalledMemory(
                text=f"NO_REPLY={os_.moves_since_reply} moves, {quiet_min} min",
                when="now",
            )
        )
    # Exactly the asset:// ids this unit prints, read off disk. She is stateless
    # between turns (`store: false`), so the map's material table is gone from
    # her context the moment the turn ends -- she remembers that pictures exist
    # and not what they are called, and invents ids Core then refuses. Listing
    # what is really there is a fact Core witnessed; which one to show is hers.
    #
    # WHOLE ids, prefix and all. This line used to strip `asset://`, and then
    # every tool that takes an asset refused the exact string Core had just
    # handed her: measured 2026-08-20 over one live period, show_image 4 of 5
    # refused and play_clip 3 of 3, all `asset-malformed`. The board stayed
    # blank for the whole lesson. A fix against invented ids that mints a
    # malformed one is worse than no fix, because the refusal now looks like
    # her mistake.
    #
    # The prefix costs ~8 chars an id on every turn. That is the price of one
    # spelling: `_as_asset` deliberately does NOT also accept a bare id, for
    # the reason show_image's own left/right comment records -- a second,
    # invisible calling convention is a coin flip a small model pays for every
    # turn. Core hands her the string the contract wants.
    catalog = os_.catalog()
    if catalog["assets"]:
        notes.append(
            RecalledMemory(
                text="ASSETS=" + ", ".join(catalog["assets"]),
                when="now",
            )
        )
    # The objective ids this unit records against, for exactly the reason the
    # assets are listed. She opens map.md on turn one and never again -- READ_NOW
    # drops it once it is in `already`, and `store: false` means she holds none
    # of it after the turn ends. From turn two her only continuity is one line
    # of PLAN and LAST_SAY, which is why the last thing she said is the best
    # predictor of the next thing she says.
    #
    # A path lookup on a file Core does not interpret. WHICH objective to work
    # on, and when to leave one, stays hers -- the map groups them by period and
    # Core must never read that grouping.
    if catalog["objectives"]:
        notes.append(
            RecalledMemory(
                text="OBJECTIVES=" + ", ".join(catalog["objectives"]),
                when="now",
            )
        )
    # Which language the answer came in. Only when a child actually spoke:
    # a heartbeat has no speaker. Core states it; scaffold-down says what it
    # is worth.
    if os_.turn_language:
        notes.append(RecalledMemory(text="ANSWERED_IN=" + os_.turn_language, when="now"))
    notes.append(RecalledMemory(text="student_id=" + os_.learner_id, when="now"))
    # An empty board is a fact, and it was invisible: the writing/images/exercise
    # lines are omitted when empty, so "nothing is up" and "I was not told" read
    # identically. Measured 2026-08-19 on google/gemma-4-26b-a4b-it: she said
    # "Look at these friends!" twice with nothing on the projector at all.
    if not (os_.last_writing or os_.last_images or os_.last_exercise):
        notes.append(RecalledMemory(text="BOARD=empty", when="now"))
    if os_.last_writing:
        notes.append(RecalledMemory(text="writing=" + os_.last_writing, when="now"))
    if os_.last_images:
        notes.append(RecalledMemory(text="images=" + json.dumps(os_.last_images, ensure_ascii=False), when="now"))
    if os_.last_clip:
        notes.append(RecalledMemory(text="clip=" + json.dumps(os_.last_clip, ensure_ascii=False), when="now"))
    if os_.last_exercise:
        notes.append(
            RecalledMemory(text="exercise=" + json.dumps(os_.last_exercise, ensure_ascii=False), when="now")
        )
    if os_.last_present:
        notes.append(RecalledMemory(text="board=" + json.dumps(os_.last_present, ensure_ascii=False), when="now"))
    if os_.reads:
        notes.append(RecalledMemory(text="reads=" + ",".join(dict.fromkeys(os_.reads)), when="now"))
    # What she has USED this period, as opposed to what is on the board right
    # now. `images=`/`clip=`/`exercise=` above are the current scene and say
    # nothing about the twenty minutes before it.
    #
    # period_census has carried exactly this since it was written, and its own
    # docstring names the reason: "No clip played all period is the finding,
    # and no single turn can show it." That finding went to /teacher/status for
    # the adult and was never once shown to the person who could act on it.
    # Measured 2026-08-20: a whole period with clips=[] beside an ASSETS= line
    # offering ten recordings, and two pictures where the map wants the picture
    # to change.
    #
    # Core is listing its own rows. WHICH recording, and whether to play one at
    # all, stays hers -- and this is the "shown state, not owned state" NS-5
    # asks for, not a transcript.
    used = [
        ("clips", os_.period_clips),
        ("images", os_.period_images),
        ("exercises", os_.period_exercises),
    ]
    notes.append(
        RecalledMemory(
            text="USED_SO_FAR=" + "; ".join(
                f"{label} {', '.join(values) if values else 'none'}" for label, values in used
            ),
            when="now",
        )
    )
    if os_.last_say:
        notes.append(RecalledMemory(text="last_teacher_line=" + os_.last_say, when="now"))
    # PLAN replaces BEATS. BEATS was a log Core wrote ABOUT her -- the last
    # eight moves -- from which she had to re-infer where she was every turn,
    # which is why teaching wandered across a period. An intention SHE wrote
    # and revises is the thing a coding agent actually keeps, and it survives
    # a restart because it lives in SQL rather than the context window.
    if os_.plan:
        notes.append(RecalledMemory(text="PLAN=" + os_.plan, when="now"))
    db = getattr(os_.core, "db", None)
    lister = getattr(db, "list_observations", None)
    if callable(lister):
        try:
            rows = list(lister(student_id=os_.learner_id) or [])
        except TypeError:
            rows = []
        card, past = format_skill_memory(rows)
        if card:
            notes.append(RecalledMemory(text="SKILL_CARD=" + card, when="now"))
        if past:
            notes.append(RecalledMemory(text="PAST=" + past, when="now"))
    return notes


BOARD_TOOLS = frozenset({"write_board", "show_image", "show_exercise"})


def _log_turn_census(os_: TeacherOS, *, event: str | None, ok: bool) -> None:
    """One line per turn: how many tools, and did anything reach the board.

    Four numbers decide, six months from now, whether the offline model is
    still teaching or has quietly become an all-talk teacher. Joined with
    `api_calls=N/8` in the harness log, `tools` also gives the bundling ratio:
    a model that stops batching pays a full round-trip per tool, and the child
    waits through every one of them.

    Names and counts only. No teacher line, no child's words, no learner id.
    """
    tools = list(os_.turn_tools)
    # `last_writing` persists across turns, so it is not proof that THIS turn
    # touched the board -- a false positive here would hide the exact
    # degradation the counter exists to catch.
    board = os_.turn_chalked or any(name in BOARD_TOOLS for name in tools)
    log.info(
        "teacher turn census event=%s ok=%s tools=%d board_touched=%s "
        "tool_names=%s refusals=%s board_skips=%s "
        "reads=%s clips=%s images=%s exercises=%s evidence=%s",
        event or "student",
        ok,
        len(tools),
        board,
        ",".join(tools) or "-",
        ",".join(os_.turn_refusals) or "-",
        ",".join(os_.turn_board_skips) or "-",
        ",".join(os_.turn_reads) or "-",
        ",".join(os_.turn_clips) or "-",
        ",".join(os_.turn_images) or "-",
        ",".join(os_.turn_exercises) or "-",
        ",".join(os_.turn_evidence) or "-",
    )


def period_census(os_: TeacherOS) -> dict[str, Any]:
    """What the whole period used, and how honest the marking looks.

    A lesson is the unit that succeeds or fails; a turn is not. "No clip played
    all period" and "every outcome was correct" are period-level findings that
    no single turn can show -- and they are exactly the two shapes the live
    failure took on 2026-08-19.

    Counts and short names only. This is safe to print on /teacher/status for
    the adult and safe to keep in a log.
    """
    outcomes: dict[str, int] = {}
    modes: dict[str, int] = {}
    objectives: list[str] = []
    for row in os_.period_evidence:
        parts = (row.split(":") + ["?", "?", "-"])[:3]
        objective, outcome, mode = parts
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        modes[mode] = modes.get(mode, 0) + 1
        if objective not in objectives:
            objectives.append(objective)
    return {
        "unit": os_.unit_id,
        "minutes": int((time.time() - os_.started_at) / 60),
        "reads": list(os_.period_reads),
        "clips": list(os_.period_clips),
        "images": list(os_.period_images),
        "exercises": list(os_.period_exercises),
        "objectives": objectives,
        "outcomes": outcomes,
        "modes": modes,
        "evidenceRows": len(os_.period_evidence),
    }


def _log_period_census(os_: TeacherOS) -> None:
    got = period_census(os_)
    log.info(
        "teacher period census unit=%s minutes=%d reads=%d clips=%d images=%d "
        "exercises=%d evidence=%d outcomes=%s modes=%s read_names=%s",
        os_.unit_id,
        int((time.time() - os_.started_at) / 60),
        len(got["reads"]),
        len(got["clips"]),
        len(got["images"]),
        len(got["exercises"]),
        got["evidenceRows"],
        json.dumps(got["outcomes"], sort_keys=True),
        json.dumps(got["modes"], sort_keys=True),
        ",".join(got["reads"]) or "-",
    )


_TURN_LOCK = asyncio.Lock()


async def handle_teacher_turn(core: Any, text: str, *, language: str | None = None) -> dict[str, Any]:
    async with _TURN_LOCK:
        return await _handle_teacher_turn(core, text, language=language)


async def _handle_teacher_turn(core: Any, text: str, *, language: str | None = None) -> dict[str, Any]:
    from bright_contracts import LastInteraction, LessonPosition, RecalledMemory, Scene, TurnContext

    os_ = getattr(core, "teacher_os", None)
    if os_ is None:
        raise RuntimeError("no teacher session")
    agent = getattr(core, "agent", None)
    if agent is None:
        raise RuntimeError("no Hermes teacher wired")
    event = system_event(text)
    os_.turn_kind = event
    os_.turn_tools = []
    os_.turn_refusals = []
    os_.turn_board_skips = []
    os_.turn_chalked = False
    os_.turn_reads = []
    os_.turn_clips = []
    os_.turn_images = []
    os_.turn_exercises = []
    os_.turn_evidence = []
    os_.turn_recorded = set()
    os_.turn_recalls = 0
    # WHICH LANGUAGE the child answered in, as the decoder heard it. A system
    # event has no speaker, so it has no language either.
    #
    # Core states the fact and rules on nothing. What it MEANS -- that a
    # beginner falling back to their home language is telling you they are
    # lost -- is pedagogy, and lives in skills/scaffold-down (NS-6).
    os_.turn_language = None if event else (language or None)
    # What Core actually heard this turn. A system event is not a child
    # speaking, so evidence written on one is about an utterance that did not
    # happen -- and she has no memory of an earlier one to be recalling.
    os_.turn_student_text = "" if event else text
    if event is None:
        os_.last_student_at = time.time()
        os_.moves_since_reply = 0
        # Someone answered. Whatever she could not reach, she has reached now.
        os_.escalated = False
    prior_say = os_.last_say
    said = None
    error = None
    for _attempt in (1, 2):
        turn_id = "bright-" + uuid.uuid4().hex
        # The TTL must outlive the model, not the other way round. The hosted
        # reasoning model has been measured at 80s for an 8-token reply and
        # ~175s before its first tool call; at the old 60s the token expired
        # before she ever used it, every tool call came back "unknown or
        # expired turn_id", the turn died mid-stream and left the provider's
        # single run open -- so the NEXT turn 429'd. The registry still scopes
        # every call to this session and learner, and the turn is retired
        # explicitly when it ends, so a long TTL costs nothing.
        os_.turn_id = turn_id
        core.turn_registry.register(
            turn_id, os_.execute, student_id=os_.learner_id, ttl_s=900.0
        )
        if getattr(agent, "wants_executor", False):
            # An in-process brain (bright_agent.relay) runs tools through the
            # same executor the turn registry got, so every refusal, every
            # census entry and every lease check is identical to a model turn.
            agent.executor = os_.execute
        prepare = getattr(agent, "prepare_turn", None)
        if callable(prepare):
            prepare(turn_id)
        ctx = TurnContext(
            stateVersion=int(core.store.state_version),
            lesson=LessonPosition(
                lessonId=os_.unit_id,
                classId="bright-one-learner",
                activityIndex=0,
                activityCount=1,
                stage="PRACTICE",
            ),
            scene=Scene(stateVersion=int(core.store.state_version), kind="text"),
            lastInteraction=LastInteraction(kind="text", detail=text, outcome=None),
            availableActions=[],
            recalled=_session_recall(os_),
        )
        said = None
        error = None
        # `frame`, not `event`: this loop used to rebind `event`, which above is
        # the SYSTEM event ("heartbeat" / "class_start" / None). By the time the
        # stream finished, `event is None` and `event == "heartbeat"` were both
        # false whatever the turn actually was -- so a heartbeat she correctly
        # answered with silence was filed as a fault. Found on 2026-08-19 by
        # the turn census printing a stream frame where the event name should
        # have been.
        async for frame in agent.turn(ctx):
            kind = getattr(frame, "type", None)
            if kind == "text_delta":
                said = getattr(frame, "text", None)
            elif kind == "done" and getattr(frame, "reason", None) == "error":
                error = getattr(frame, "detail", None)
        core.turn_registry.retire(turn_id)
        # Core-validated line from THIS turn wins. Do not replay the previous say.
        if os_.last_say and os_.last_say != prior_say:
            said = os_.last_say
        elif said and _check_teacher_line(str(said)):
            error = error or _check_teacher_line(str(said))
            said = None
        if event == "wake":
            # She asked for this beat. If she produced nothing there is nothing
            # to retry -- the room simply goes back to waiting for a child.
            if said:
                error = None
            break
        if event == "prepare":
            # Nobody is waiting, and she must not speak. The turn succeeded if
            # she wrote a plan; there is nothing to retry if she did not.
            break
        if said:
            error = None
            break
        if error and "429" in str(error):
            break
    if _is_heartbeat_ok(str(said or "")):
        said = None
        error = None
    if event == "prepare":
        # A prepare turn that produced a plan is a success even though the room
        # heard nothing -- which is the point of preparing.
        silent_ok = bool(os_.plan) and not error
        error = error or (None if silent_ok else "prepared nothing")
    else:
        silent_ok = event == "heartbeat" and not said and not error
    if said or silent_ok:
        core.last_teacher_fault = None
    else:
        core.last_teacher_fault = {
            "error": str(error or "no teacher line"),
            "unitId": os_.unit_id,
            "learnerId": os_.learner_id,
        }
    _log_turn_census(os_, event=event, ok=bool(said) or silent_ok)
    os_.turn_kind = None
    os_.turn_id = None
    os_.turn_student_text = ""
    return {
        "ok": bool(said) or silent_ok,
        "say": said,
        "present": os_.last_present,
        "writing": os_.last_writing,
        "images": dict(os_.last_images),
        "clip": os_.last_clip,
        "exercise": dict(os_.last_exercise) if os_.last_exercise else None,
        "evidence": list(os_.evidence),
        "reads": list(os_.reads),
        "error": error,
        "event": event,
        "action": "HEARTBEAT_OK" if silent_ok else ("say" if said else None),
    }


def _silence_s(os_: TeacherOS) -> float:
    marks = [os_.started_at, os_.last_say_at, os_.last_student_at, os_.last_heartbeat_at]
    last = max((mark for mark in marks if mark), default=time.time())
    return max(0.0, time.time() - last)


def _periods_held(core: Any, os_: Any) -> int | None:
    """Finished periods for this class on this unit, or None if unknowable.

    Same call `_session_recall` makes for PERIODS_HELD, and it must stay a
    count: what meeting #N *means* is in the unit map, and Core never looks it
    up. Never raises -- a missing number must not cost the adult the page.
    """
    if os_ is None:
        return None
    counter = getattr(getattr(core, "db", None), "count_periods_held", None)
    if not callable(counter):
        return None
    try:
        return int(counter(student_id=os_.learner_id, lesson_id=os_.unit_id))
    except Exception:  # noqa: BLE001 -- status is diagnosis; it must always render
        return None


def teacher_phase(core: Any) -> str:
    os_ = getattr(core, "teacher_os", None)
    if os_ is None:
        return "asleep"
    if _TURN_LOCK.locked():
        return "thinking"
    if not hermes_up():
        return "fault"
    return "listening"


def teacher_status_payload(core: Any) -> dict[str, Any]:
    os_ = getattr(core, "teacher_os", None)
    fault = getattr(core, "last_teacher_fault", None)
    leases = getattr(core, "capability_leases", None)
    if leases is not None:
        leases.expire()
    stage = bool(leases and getattr(leases, "stage_owner", None))
    hermes = hermes_up()
    speech = speech_up()
    return {
        "ok": os_ is not None,
        "unitId": getattr(os_, "unit_id", None),
        "learnerId": getattr(os_, "learner_id", None),
        "hasBoard": bool(getattr(os_, "last_writing", None) or getattr(os_, "last_images", None)),
        "lastFault": fault,
        "lastSay": getattr(os_, "last_say", None),
        "stageAudioOwner": stage,
        "speechUp": speech,
        "hermesUp": hermes,
        "readyToStart": hermes and stage,
        "sessionOpen": os_ is not None,
        "phase": teacher_phase(core),
        "silenceMs": int(_silence_s(os_) * 1000) if os_ is not None else 0,
        "turnBusy": _TURN_LOCK.locked(),
        # For the adult, not for the room: what she says she is doing. Nothing
        # in Core reads this string to decide anything.
        "plan": getattr(os_, "plan", None) or None,
        # How many periods this class has finished on this unit. Core counts;
        # the map says what meeting #N means. It is here because without it a
        # run cannot be read: on 2026-08-20 she was scored FAIL on "put up an
        # exercise" while correctly teaching Period 2, for which no exercise
        # was authored -- and nothing on this payload said which period it was.
        "periodsHeld": _periods_held(core, os_),
        # What this period has actually used so far. The adult can see a lesson
        # that has played no recording and shown one picture before it ends.
        "period": period_census(os_) if os_ is not None else None,
        # A scheduled job that fails at 03:00 and tells nobody is the
        # papered-over failure the doctrine calls a defect.
        "lastPrepare": getattr(core, "last_prepare", None),
        # The one thing on this page that is not observability: she has stopped
        # teaching and is asking for a person.
        "escalation": getattr(core, "escalation", None),
        "pausedByAdult": getattr(core, "paused_by_adult", None),
    }


async def _open_on_presence(core: Any, *, reason: str) -> dict[str, Any] | None:
    """Open the class because the room is there, not because a hand pressed a button.

    NS-1: the adult boots the appliance and walks away. The Stage already
    announces itself and claims the audio lease every few seconds; the pulse
    already ticks. The only reason nothing used to happen is that
    ``start_teacher_session`` had exactly one caller -- the Start pill.

    Returns None when the room is not ready, so the pulse falls through to its
    ordinary "asleep" answer and tries again on the next tick. Never raises:
    a projector that cannot open a class must still stay up and be honest
    about it on /teacher/status.
    """
    closed_at = getattr(core, "last_close_at", None)
    if closed_at is not None and (time.time() - closed_at) < REOPEN_AFTER_CLOSE_S:
        return None          # she just closed this period; do not reopen it

    leases = getattr(core, "capability_leases", None)
    if leases is not None:
        leases.expire()
    if not (leases and getattr(leases, "stage_owner", None)):
        return None          # nobody is in the room, or the projector is dark
    if not speech_up():
        return None          # she would be mute; wait rather than greet silently
    if not hermes_up():
        return None          # no teacher to open the class; the pulse retries



    from library import list_units

    units = list_units()
    if len(units) != 1:
        # Core must never pick a favourite lesson (NS-7). With none authored
        # there is nothing to teach; with several, an adult chooses.
        return None
    settings = getattr(core, "settings", None)
    # NS-7: a child's name is a property of the deployment, never of the code.
    learner_id = str(getattr(settings, "default_learner_id", "") or "learner")
    learner_name = str(getattr(settings, "default_learner_name", "") or "Learner")
    # WHO is this, if the room can see. A confident, fresh match opens that
    # child's session and therefore that child's recorded evidence; anything
    # less falls through to the declared learner, because "uncertain identity
    # means no student-memory write" and opening the wrong child's memory is
    # the same mistake made earlier. Core never sees the face -- perception
    # hands over an id (docs/decisions/2026-08-20-the-room-knows-who.md).
    seen = getattr(core, "identified_learner", None)
    if seen is not None and seen.fresh():
        learner_id, learner_name = seen.student_id, seen.display_name
        log.info("presence: recognised %s (%.2f)", learner_id, seen.similarity)
    try:
        # An interrupted period is resumed, not replaced. `[heartbeat]` tells her
        # to look up and carry on; `[sat_down]` would make her greet a class she
        # is already teaching.
        resumed = resume_teacher_session(core)
        opening = "[heartbeat]"
        if resumed is None:
            start_teacher_session(
                core, unit_id=units[0], learner_id=learner_id, learner_name=learner_name
            )
            opening = "[sat_down]"
        result = await handle_teacher_turn(core, opening)
    except Exception as exc:  # noqa: BLE001 -- the room outlives the brain
        core.teacher_os = None
        core.last_teacher_fault = {"error": f"could not open the class: {exc}"}
        return {"ok": False, "action": "wait", "phase": "fault", "reason": "open_failed"}
    result["reason"] = f"presence:{reason}"
    result["phase"] = teacher_phase(core)
    if not result.get("action"):
        result["action"] = "say" if result.get("say") else HEARTBEAT_OK
    return result


async def pulse_teacher(core: Any, *, force: bool = False, reason: str = "tick") -> dict[str, Any]:
    """OpenClaw-style wake: check, maybe run one main-session turn, or stay quiet."""
    if _TURN_LOCK.locked():
        return {"ok": True, "action": "busy", "phase": "thinking", "reason": reason}
    os_ = getattr(core, "teacher_os", None)
    if os_ is None:
        opened = await _open_on_presence(core, reason=reason)
        if opened is not None:
            return opened
        return {"ok": True, "action": "asleep", "phase": "asleep", "reason": reason}
    if _TURN_LOCK.locked():
        return {"ok": True, "action": "busy", "phase": "thinking", "reason": reason}

    # Nobody is there.
    #
    # The stage lease was only ever checked on the way IN (`_open_on_presence`).
    # Once a session was open the pulse kept taking turns with no such check, so
    # a room whose projector had been closed went on being taught: she asked
    # questions into an empty room, nudged, waited, nudged again, and every one
    # of those was a model turn nobody heard. It could not happen before because
    # there was no way out of `/classroom` -- there is now, so this is the guard
    # that makes a door safe.
    #
    # It is a presence FACT, the same one that opens the class, read the same
    # way. Core is not deciding anything about the lesson: the session stays
    # open, and walking back in re-attaches to the same period.
    leases = getattr(core, "capability_leases", None)
    if leases is not None:
        leases.expire()
        if not getattr(leases, "stage_owner", None):
            return {"ok": True, "action": "empty_room", "phase": "asleep", "reason": "no_stage"}

    if not hermes_up():
        return {"ok": False, "action": "wait", "phase": "fault", "reason": "hermes"}
    silence = _silence_s(os_)
    now = time.time()

    # She asked something and is waiting. Nudge once, early, then let the
    # ordinary long floor take over -- and bypass HEARTBEAT_MIN_GAP_S for that
    # one nudge, or the 20s cooldown swallows the whole point of a short wait.
    # A beat she scheduled herself. It bypasses the silence floor and the
    # cooldown, like the nudge -- the whole point is that it happens when she
    # said, not when the room happens to go quiet. It is NOT a heartbeat: a
    # heartbeat may honestly answer HEARTBEAT_OK and stay silent, which for a
    # move she asked for would be the drill dying mid-round.
    if os_.wake_at is not None and now >= os_.wake_at:
        os_.wake_at = None
        os_.last_heartbeat_at = now
        try:
            result = await handle_teacher_turn(core, "[wake]")
        except RuntimeError as exc:
            return {"ok": False, "action": "wait", "phase": "fault", "reason": str(exc)}
        result["silenceMs"] = int(_silence_s(os_) * 1000)
        result["phase"] = teacher_phase(core)
        result["reason"] = "her_own_next_beat"
        if not result.get("action"):
            result["action"] = "say" if result.get("say") else HEARTBEAT_OK
        return result

    nudging = os_.awaiting_answer and not os_.nudged_once and silence >= WAIT_AFTER_QUESTION_S
    if nudging:
        os_.nudged_once = True
        os_.last_heartbeat_at = now
        try:
            result = await handle_teacher_turn(core, "[heartbeat]")
        except RuntimeError as exc:
            return {"ok": False, "action": "wait", "phase": "fault", "reason": str(exc)}
        result["silenceMs"] = int(_silence_s(os_) * 1000)
        result["phase"] = teacher_phase(core)
        result["reason"] = "waiting_for_an_answer"
        if not result.get("action"):
            result["action"] = "say" if result.get("say") else HEARTBEAT_OK
        return result

    # Whichever silence this is, Core witnessed which -- she set awaiting_answer
    # herself on her last say. Core is not deciding what to teach; it is
    # reporting which of two states it saw, the same way it reports BOARD=empty.
    # She has handed the room over and is waiting for a person. Do not keep
    # giving her the floor: measured 2026-08-19, she called the adult on three
    # consecutive turns, which is an alarm that repeats every twelve seconds
    # and therefore an alarm nobody reads. The room stays exactly as it is; a
    # child speaking is the one thing that brings her back, because that is a
    # class she can reach after all.
    # The adult has taken the room. Nothing the teacher does may reach it until
    # a person gives it back -- that is what "the facilitator is the safety
    # authority" means when it is a mechanism rather than a sentence.
    if getattr(core, "paused_by_adult", None):
        return {
            "ok": True,
            "action": HEARTBEAT_OK,
            "phase": "fault",
            "reason": "paused_by_the_adult",
            "silenceMs": int(silence * 1000),
        }

    if getattr(os_, "escalated", False):
        # Logged once a tick on purpose: an adult reading the service log
        # should be able to see that the room is waiting for them, not stuck.
        log.info("pulse held: the room is waiting for the adult")
        return {
            "ok": True,
            "action": HEARTBEAT_OK,
            "phase": "fault",
            "reason": "waiting_for_the_adult",
            "silenceMs": int(silence * 1000),
        }

    # She asked, the early nudge went, and still nothing came back. A real
    # teacher does not stand at the front of the room waiting indefinitely --
    # she models the answer, runs it chorally, tries another way. So the wait
    # EXPIRES: once nudged and still silent past the patient floor, the room
    # stops calling it "they are thinking" and hands her the floor.
    #
    # Measured 2026-08-19 without this: she set awaiting_answer on her opening
    # line and every subsequent turn was a heartbeat, forever, one line each.
    still_waiting = os_.awaiting_answer and not (
        os_.nudged_once and silence >= HEARTBEAT_SILENCE_S
    )
    floor = HEARTBEAT_SILENCE_S if still_waiting else HEARTBEAT_FLOOR_IS_HERS_S
    if not force and silence < floor:
        return {
            "ok": True,
            "action": HEARTBEAT_OK,
            "phase": "listening",
            "reason": "recent",
            "silenceMs": int(silence * 1000),
        }
    last_hb = os_.last_heartbeat_at
    if not force and last_hb is not None and (now - last_hb) < HEARTBEAT_MIN_GAP_S:
        return {
            "ok": True,
            "action": HEARTBEAT_OK,
            "phase": "listening",
            "reason": "cooldown",
            "silenceMs": int(silence * 1000),
        }
    os_.last_heartbeat_at = now
    # `[floor]` when the room is quiet and she was not waiting for anyone: this
    # is her turn to move, and the HEARTBEAT_OK escape hatch is wrong for it.
    # `[heartbeat]` keeps its meaning -- the class is thinking, do not interrupt.
    token = "[heartbeat]" if still_waiting else "[floor]"
    if not still_waiting:
        # The question has been answered by silence. Stop re-asking it.
        os_.awaiting_answer = False
    try:
        result = await handle_teacher_turn(core, token)
    except RuntimeError as exc:
        return {"ok": False, "action": "wait", "phase": "fault", "reason": str(exc)}
    result["silenceMs"] = int(_silence_s(os_) * 1000)
    result["phase"] = teacher_phase(core)
    result["reason"] = reason
    if not result.get("action"):
        result["action"] = "say" if result.get("say") else HEARTBEAT_OK
    return result


async def teacher_heartbeat_loop(core: Any) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_TICK_S)
        try:
            await pulse_teacher(core, reason="tick")
        except asyncio.CancelledError:
            raise
        except Exception:
            # A pulse must never take the room down.
            continue
