#!/usr/bin/env python3
"""Pure fleet run admission law. No I/O, routing, policy grants or device access.

The registry/probe/source-transfer adapters supply observations; this reducer
only decides if a selected, qualified remote may be prepared or executed.
Never treat evidence, a proof verdict or an old permission as authorization.
See bend/fleet_admission/MODEL.bend and the exhaustive parity fixture.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Target(str, Enum):
    MISSING = "missing"
    GROOT = "groot"
    REMOTE = "remote"


class Transfer(str, Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    NOT_REQUIRED = "not_required"
    FAILED = "failed"


class Reason(str, Enum):
    NO_REMOTE = "NO_REMOTE"
    GROOT_FORBIDDEN = "GROOT_FORBIDDEN"
    UNQUALIFIED = "UNQUALIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    NO_ROOM = "NO_ROOM"
    SOURCE_TRANSFER_FAILED = "SOURCE_TRANSFER_FAILED"


@dataclass(frozen=True)
class Request:
    target: Target
    qualified: bool
    available: bool
    room: bool
    transfer: Transfer


@dataclass(frozen=True)
class Refuse:
    reason: Reason


@dataclass(frozen=True)
class Prepare:
    """Remote selected; source has not been attested as delivered."""


@dataclass(frozen=True)
class Admit:
    """Source delivered (or explicitly not required); remote execution allowed."""


Verdict = Refuse | Prepare | Admit

_MESSAGES = {
    Reason.NO_REMOTE: "no registered remote worker selected",
    Reason.GROOT_FORBIDDEN: "groot is not a fleet host lane",
    Reason.UNQUALIFIED: "remote does not meet class, arch, health or taint requirements",
    Reason.UNAVAILABLE: "remote is unreachable, has invalid probe data or is cordoned",
    Reason.NO_ROOM: "qualified remote has insufficient memory or lane capacity",
    Reason.SOURCE_TRANSFER_FAILED: "source was not successfully delivered to the remote",
}


def decide(request: Request) -> Verdict:
    """Closed finite domain; no fallback action or implicit execution path."""
    # External registry/CLI data must be mapped into the closed model explicitly.
    # Do not interpret a malformed node/transfer/boolean as a positive remote.
    if not isinstance(request.target, Target):
        return Refuse(Reason.NO_REMOTE)
    if any(type(v) is not bool for v in (request.qualified, request.available, request.room)):
        return Refuse(Reason.UNQUALIFIED)
    if not isinstance(request.transfer, Transfer):
        return Refuse(Reason.SOURCE_TRANSFER_FAILED)
    if request.target is Target.MISSING:
        return Refuse(Reason.NO_REMOTE)
    if request.target is Target.GROOT:
        return Refuse(Reason.GROOT_FORBIDDEN)
    if not request.qualified:
        return Refuse(Reason.UNQUALIFIED)
    if not request.available:
        return Refuse(Reason.UNAVAILABLE)
    if not request.room:
        return Refuse(Reason.NO_ROOM)
    if request.transfer is Transfer.FAILED:
        return Refuse(Reason.SOURCE_TRANSFER_FAILED)
    if request.transfer is Transfer.PENDING:
        return Prepare()
    if request.transfer in (Transfer.COMPLETE, Transfer.NOT_REQUIRED):
        return Admit()
    raise TypeError("unknown transfer state; refusing to execute")


def reason_text(refusal: Refuse, detail: str = "") -> str:
    """Nonempty typed admission/transfer reason, safe for stderr and shell."""
    if not isinstance(refusal, Refuse) or not isinstance(refusal.reason, Reason):
        raise TypeError("reason_text accepts only typed Refuse")
    extra = ("; " + detail) if detail else ""
    return f"Refuse[{refusal.reason.value}]: {_MESSAGES[refusal.reason]}{extra}"


def verdict_code(verdict: Verdict) -> int:
    """Parity-only projection. Never use the numeric code as an execution grant."""
    if isinstance(verdict, Refuse):
        return list(Reason).index(verdict.reason)
    if isinstance(verdict, Prepare):
        return 6
    if isinstance(verdict, Admit):
        return 7
    raise TypeError("invalid verdict")
