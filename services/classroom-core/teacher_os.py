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
}
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
HEARTBEAT_SILENCE_S = 45.0
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
    started_at: float = field(default_factory=time.time)
    last_say_at: float | None = None
    awaiting_answer: bool = False
    nudged_once: bool = False
    last_student_at: float | None = None
    last_heartbeat_at: float | None = None
    turn_kind: str | None = None

    def map_path(self) -> str:
        return f"units/{self.unit_id}/map.md"

    def close_period(self) -> None:
        """End the period: close the row, drop the OS, mark the clock."""
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
        caption = (self.last_say or "").strip()[:80]
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
            board = str(result.get("board") or "")
            if board == "applied":
                self.turn_chalked = True
            elif board.startswith("skipped:"):
                self.turn_board_skips.append(_reason_class(board))
        return result

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
            content = arguments.get("content")
            if kind not in EXERCISE_KINDS:
                return {"ok": False, "reason": "kind must be choice, vocabulary, or roleplay"}
            if not isinstance(content, dict):
                return {"ok": False, "reason": "content must be an object"}
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
            if board_text:
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
            # She tells us whether she just asked something. Core does not
            # guess it from a question mark -- "Now you try" expects an answer
            # and carries no "?", while "How are you?" modelled aloud does not.
            self.awaiting_answer = bool(arguments.get("awaiting_answer"))
            self.nudged_once = False
            publish = getattr(self.core, "publish_speech", None)
            if callable(publish):
                publish(line, source="agent")
            if bool(arguments.get("closing")):
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

        if name == "record_evidence":
            if self.turn_kind == "heartbeat":
                return {"ok": False, "reason": "heartbeat is not student evidence"}
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
            if mode and mode not in MODES:
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
            db = getattr(self.core, "db", None)
            record = getattr(db, "record_observation", None)
            if callable(record):
                payload = dict(
                    session_id=getattr(self.core, "session_id", None),
                    response_turn_id=f"ev-{uuid.uuid4().hex[:12]}",
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
REOPEN_AFTER_CLOSE_S = 600.0


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
    return {"ok": bool(got.get("ok")), "unitId": unit_id, "error": got.get("error")}


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
    notes.append(RecalledMemory(text="student_id=" + os_.learner_id, when="now"))
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
        "tool_names=%s refusals=%s board_skips=%s",
        event or "student",
        ok,
        len(tools),
        board,
        ",".join(tools) or "-",
        ",".join(os_.turn_refusals) or "-",
        ",".join(os_.turn_board_skips) or "-",
    )


_TURN_LOCK = asyncio.Lock()


async def handle_teacher_turn(core: Any, text: str) -> dict[str, Any]:
    async with _TURN_LOCK:
        return await _handle_teacher_turn(core, text)


async def _handle_teacher_turn(core: Any, text: str) -> dict[str, Any]:
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
    if event is None:
        os_.last_student_at = time.time()
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
        core.turn_registry.register(
            turn_id, os_.execute, student_id=os_.learner_id, ttl_s=900.0
        )
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
        # A scheduled job that fails at 03:00 and tells nobody is the
        # papered-over failure the doctrine calls a defect.
        "lastPrepare": getattr(core, "last_prepare", None),
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
    if not hermes_up():
        return {"ok": False, "action": "wait", "phase": "fault", "reason": "hermes"}
    silence = _silence_s(os_)
    now = time.time()

    # She asked something and is waiting. Nudge once, early, then let the
    # ordinary long floor take over -- and bypass HEARTBEAT_MIN_GAP_S for that
    # one nudge, or the 20s cooldown swallows the whole point of a short wait.
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

    if not force and silence < HEARTBEAT_SILENCE_S:
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
    try:
        result = await handle_teacher_turn(core, "[heartbeat]")
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
