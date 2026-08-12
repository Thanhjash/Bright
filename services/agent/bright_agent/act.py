"""ACT tokens — emission side.

PROTOCOL.md §5. Tokens ride **inline in the text stream** so they stay
ordered against the audio and fire in sync with speech. This module only
*emits*; parsing (the 5-char tail rule, back-pressure) belongs to
packages/airi-bridge.

Two jobs:
  1. render an `ActPayload` as `<|ACT {...}|>`
  2. map tool activity to emotions, exactly per §5's adapter table
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Iterable

from bright_contracts import EMOTION_MOTION_GROUP, ActPayload, Emotion, EmotionSpec, TAG_CLOSE, TAG_OPEN

from .base import Act, AgentEvent, TextDelta
from .tools import CHOOSE_NEXT, GET_STATE, RECALL, RECORD_OBSERVATION

#: The only legal emotions. Anything else is a bug, not a fallback.
EMOTIONS: tuple[str, ...] = tuple(EMOTION_MOTION_GROUP.keys())


def motion_group(emotion: Emotion) -> str:
    """Live2D motion group for an emotion. `neutral` -> `Idle`, not `Neutral`."""
    return EMOTION_MOTION_GROUP[emotion]


def make_act(
    emotion: Emotion | None = None,
    *,
    motion: str | None = None,
    intensity: float = 1.0,
) -> ActPayload:
    if emotion is not None and emotion not in EMOTION_MOTION_GROUP:
        raise ValueError(f"{emotion!r} is not one of the 9 emotions: {EMOTIONS}")
    if intensity != 1.0 and emotion is not None:
        return ActPayload(emotion=EmotionSpec(name=emotion, intensity=intensity), motion=motion)
    return ActPayload(emotion=emotion, motion=motion)


def format_act(payload: ActPayload) -> str:
    """`<|ACT {"emotion":"happy","motion":"nod"}|>` — compact, no spaces."""
    body: dict[str, Any] = {}
    if payload.emotion is not None:
        if isinstance(payload.emotion, EmotionSpec):
            body["emotion"] = {
                "name": payload.emotion.name,
                "intensity": payload.emotion.intensity,
            }
        else:
            body["emotion"] = payload.emotion
    if payload.motion:
        body["motion"] = payload.motion
    return f"{TAG_OPEN}ACT {json.dumps(body, separators=(',', ':'))}{TAG_CLOSE}"


def format_delay(seconds: float) -> str:
    """`<|DELAY 1.5|>` — a bare positive number, space separated."""
    if seconds <= 0:
        raise ValueError("DELAY must be positive")
    return f"{TAG_OPEN}DELAY {seconds:g}{TAG_CLOSE}"


def act_event(
    emotion: Emotion | None = None, *, motion: str | None = None, intensity: float = 1.0
) -> Act:
    payload = make_act(emotion, motion=motion, intensity=intensity)
    return Act(act=payload, inline=format_act(payload))


# ------------------------------------------------- tool activity -> emotion

#: PROTOCOL.md §5, "How the adapter generates them".
_RESULT_EMOTION: dict[str, Emotion] = {
    "correct": "happy",
    "near": "curious",
    "wrong": "curious",
    "silence": "question",
}

#: A board-changing call makes the avatar think; a lookup does too.
_THINKING_TOOLS = (GET_STATE, CHOOSE_NEXT, RECALL, RECORD_OBSERVATION)


def outcome_emotion(result: str | None) -> Emotion | None:
    return _RESULT_EMOTION.get(result or "")


class ActEmitter:
    """Per-turn emotion state machine. One instance per `turn()`.

    Dedupes `think` to once per turn (§5: "once per turn, deduped"), so a
    three-round tool loop does not make the avatar stutter.
    """

    def __init__(self) -> None:
        self._thought = False
        self._closed = False

    def on_tool_call(self, name: str) -> Act | None:
        if name not in _THINKING_TOOLS or self._thought:
            return None
        self._thought = True
        return act_event("think")

    def on_tool_result(self, name: str, result: Any) -> Act | None:
        """Correct answer -> happy, wrong -> curious. Only grading tools speak."""
        if name != RECORD_OBSERVATION:
            return None
        outcome = None
        if isinstance(result, dict):
            outcome = result.get("result") or result.get("outcome")
        if outcome is None and isinstance(result, str):
            outcome = result
        emotion = outcome_emotion(outcome)
        return act_event(emotion) if emotion else None

    def on_done(self) -> Act | None:
        """`response.completed` -> neutral. Emitted once."""
        if self._closed:
            return None
        self._closed = True
        return act_event("neutral")


# --------------------------------------------------- one merged text stream


async def to_text_stream(events: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    """Flatten an `AgentEvent` stream into the single annotated text stream
    the avatar/TTS pipeline consumes: spoken text with `<|ACT|>` tokens
    interleaved in the order they occurred.

    `DirectAgent` yields `Act` as its own event rather than smuggling the
    token into a `TextDelta`, so consumers that do not parse text still see
    emotion. This helper is for the consumers that do.
    """
    async for ev in events:
        if isinstance(ev, TextDelta):
            if ev.text:
                yield ev.text
        elif isinstance(ev, Act):
            yield ev.inline or format_act(ev.act)


def annotate(text: str, *, before: Iterable[ActPayload] = (), after: Iterable[ActPayload] = ()) -> str:
    """Wrap a line of speech in ACT tokens. Handy for templated narration."""
    head = "".join(format_act(p) for p in before)
    tail = "".join(format_act(p) for p in after)
    return f"{head}{text}{tail}"


__all__ = [
    "EMOTIONS",
    "motion_group",
    "make_act",
    "format_act",
    "format_delay",
    "act_event",
    "outcome_emotion",
    "ActEmitter",
    "to_text_stream",
    "annotate",
]
