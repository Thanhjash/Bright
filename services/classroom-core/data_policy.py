"""Typed, fail-closed policy for data sent to a teacher model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DataPolicy(StrEnum):
    HOSTED_SEMANTIC = "hosted_semantic"
    HOSTED_EPHEMERAL_TRANSCRIPT = "hosted_ephemeral_transcript"
    SYNTHETIC_DEV = "synthetic_dev"
    LOCAL_TRUSTED = "local_trusted"

    @classmethod
    def parse(cls, value: str | None) -> "DataPolicy":
        aliases = {
            "hosted-minimal": cls.HOSTED_SEMANTIC,
            "hosted_semantic": cls.HOSTED_SEMANTIC,
            "hosted-ephemeral-transcript": cls.HOSTED_EPHEMERAL_TRANSCRIPT,
            "hosted_ephemeral_transcript": cls.HOSTED_EPHEMERAL_TRANSCRIPT,
            "synthetic-dev": cls.SYNTHETIC_DEV,
            "synthetic_dev": cls.SYNTHETIC_DEV,
            "local-trusted": cls.LOCAL_TRUSTED,
            "local_trusted": cls.LOCAL_TRUSTED,
        }
        return aliases.get(str(value or "").strip().lower(), cls.HOSTED_SEMANTIC)


@dataclass(frozen=True, slots=True)
class OutboundInteraction:
    """The complete allowlist for one provider-visible interaction."""

    activity_id: str
    response_kind: str
    outcome: str
    option_id: str | None = None
    target_id: str | None = None
    from_id: str | None = None
    to_id: str | None = None
    ephemeral_transcript: str | None = None

    def render(self) -> str:
        fields: list[tuple[str, str | None]] = [
            ("activity", self.activity_id),
            ("response_kind", self.response_kind),
            ("outcome", self.outcome),
            ("option_id", self.option_id),
            ("target_id", self.target_id),
            ("from_id", self.from_id),
            ("to_id", self.to_id),
            ("ephemeral_transcript", self.ephemeral_transcript),
        ]
        return "; ".join(f"{key}={value}" for key, value in fields if value not in (None, ""))


def outbound_interaction(
    *,
    policy: DataPolicy | str,
    activity_id: str,
    response_kind: str,
    outcome: str,
    payload: dict[str, Any],
) -> OutboundInteraction:
    """Reduce an untrusted response payload to the provider allowlist.

    Raw text is included only for an explicitly acknowledged hosted ephemeral
    run, or when both the process is in ``synthetic_dev`` and the event is
    explicitly marked synthetic. A browser cannot smuggle a transcript out by
    merely adding a ``studentId`` or arbitrary field.
    """
    mode = policy if isinstance(policy, DataPolicy) else DataPolicy.parse(policy)
    ephemeral_text: str | None = None
    if mode == DataPolicy.HOSTED_EPHEMERAL_TRANSCRIPT:
        # This is deliberately a current-turn field. Callers must never copy
        # the rendered interaction into observations, memory, summaries or
        # durable evidence. The startup guard in app.py requires an explicit
        # operator acknowledgement before this policy can be selected.
        ephemeral_text = str(payload.get("text") or "")[:500] or None
    if (
        mode == DataPolicy.SYNTHETIC_DEV
        and payload.get("synthetic") is True
        and isinstance(payload.get("syntheticFixtureId"), str)
        and payload["syntheticFixtureId"].strip()
    ):
        ephemeral_text = str(payload.get("text") or "")[:500] or None
    return OutboundInteraction(
        activity_id=activity_id,
        response_kind=response_kind,
        outcome=outcome,
        option_id=str(payload.get("optionId")) if payload.get("optionId") else None,
        target_id=str(payload.get("targetId")) if payload.get("targetId") else None,
        from_id=str(payload.get("fromId")) if payload.get("fromId") else None,
        to_id=str(payload.get("toId")) if payload.get("toId") else None,
        ephemeral_transcript=ephemeral_text,
    )


__all__ = ["DataPolicy", "OutboundInteraction", "outbound_interaction"]
