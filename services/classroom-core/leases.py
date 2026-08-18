"""Capability leases — who in the room owns the speaker and the input.

Extracted from the retired lesson-graph controller on 2026-08-18. This is the
only part of that module the teacher agent needs: the Stage must claim the audio
lease before Piper will speak, and exactly one connection may own it.

There is no second loudspeaker. That rule lives here.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any


class AssignmentRejected(RuntimeError):
    """A response did not possess the current Core-issued capability."""


@dataclass(slots=True)
class StageLease:
    lease_id: str
    subscriber_id: int
    client_instance_id: str
    connection_epoch: int
    expires_at: float
    capabilities: dict[str, bool | str | int | float]


class CapabilityLeaseRegistry:
    """Server-time capabilities and the single active Stage audio owner."""

    def __init__(self, core: Any, *, ttl_s: float = 45.0) -> None:
        self.core = core
        self.ttl_s = max(2.0, float(ttl_s))
        self.reports: dict[int, StageLease] = {}
        self.stage_owner: StageLease | None = None
        self.control_input_owner: StageLease | None = None

    def report(self, sub: Any, payload: Any) -> StageLease | None:
        self.expire()
        if payload.role != sub.role:
            raise AssignmentRejected("capability role does not match immutable socket role")
        previous = self.reports.get(sub.id)
        if previous is not None and (
            previous.client_instance_id != payload.client_instance_id
            or payload.connection_epoch < previous.connection_epoch
        ):
            raise AssignmentRejected("client instance or connection epoch regressed")
        lease = StageLease(
            lease_id="stage-lease-" + secrets.token_urlsafe(16),
            subscriber_id=sub.id,
            client_instance_id=payload.client_instance_id,
            connection_epoch=payload.connection_epoch,
            expires_at=time.monotonic() + self.ttl_s,
            capabilities=dict(payload.capabilities),
        )
        self.reports[sub.id] = lease
        if sub.role == "control":
            input_ready = bool(
                lease.capabilities.get("audioCapture")
                or lease.capabilities.get("microphone")
                or lease.capabilities.get("audio_input")
            )
            if not input_ready:
                if self.control_input_owner and self.control_input_owner.subscriber_id == sub.id:
                    self.control_input_owner = None
                return None
            if self.control_input_owner is None or self.control_input_owner.subscriber_id == sub.id:
                self.control_input_owner = lease
            return None
        if sub.role != "stage":
            return None
        audio_ready = bool(
            lease.capabilities.get("audioPlayback")
            or lease.capabilities.get("speechPlayback")
            or lease.capabilities.get("audio_output")
        )
        if not audio_ready:
            if self.stage_owner and self.stage_owner.subscriber_id == sub.id:
                self.stage_owner = None
            return None
        if self.stage_owner is None or self.stage_owner.subscriber_id == sub.id:
            self.stage_owner = lease
            return lease
        return None

    def owns_audio(self, sub: Any) -> bool:
        self.expire()
        return self.stage_owner is not None and self.stage_owner.subscriber_id == sub.id

    def owns_input(self, sub: Any) -> bool:
        self.expire()
        return (
            self.control_input_owner is not None
            and self.control_input_owner.subscriber_id == sub.id
        )

    def disconnect(self, sub: Any) -> None:
        self.reports.pop(sub.id, None)
        if self.stage_owner is not None and self.stage_owner.subscriber_id == sub.id:
            self.stage_owner = None
        if self.control_input_owner is not None and self.control_input_owner.subscriber_id == sub.id:
            self.control_input_owner = None

    def expire(self) -> None:
        now = time.monotonic()
        expired = [sub_id for sub_id, lease in self.reports.items() if lease.expires_at <= now]
        owner_expired = self.stage_owner is not None and self.stage_owner.expires_at <= now
        input_expired = (
            self.control_input_owner is not None
            and self.control_input_owner.expires_at <= now
        )
        for sub_id in expired:
            self.reports.pop(sub_id, None)
        if owner_expired:
            self.stage_owner = None
        if input_expired:
            self.control_input_owner = None
