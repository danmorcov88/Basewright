"""Deciding whether a host is fit to run what was asked for.

Twenty rules apply to every engine and are written here; a profile contributes as many
more as it needs, as expressions. Both kinds produce the same result and are resolved
against the same two severities, so a report cannot suggest that one sort of rule counts
for less than the other.

A block produces a refusal and nothing else. There is no flag that turns one into a
warning, here or anywhere: if a block is wrong then the rule is wrong, and the rule is
fixed in Git where somebody can see the change.
"""

from __future__ import annotations

from typing import Any

from basewright import __version__
from basewright.preflight.engine import RuleError, evaluate
from basewright.preflight.model import (
    GateResult,
    Outcome,
    PreflightResult,
    Severity,
    Source,
    Verdict,
)
from basewright.preflight.shared import SHARED_RULES
from basewright.profiles.model import Profile
from basewright.request import Request

__all__ = [
    "SHARED_RULES",
    "GateResult",
    "Outcome",
    "PreflightResult",
    "RuleError",
    "Severity",
    "Source",
    "Verdict",
    "document",
    "evaluate",
]


def document(result: PreflightResult, profile: Profile, request: Request) -> dict[str, Any]:
    """The run as ``preflight.schema.json`` describes it.

    Written whether or not anything blocked. A refusal is a first-class outcome, so it has
    an artifact of its own rather than being the absence of a plan.
    """
    return {
        "schema_version": "1",
        "evaluated_at": f"{result.evaluated_at:%Y-%m-%dT%H:%M:%S}Z",
        "tool_version": __version__,
        "profile": {"engine": profile.engine, "version": profile.profile_version},
        "request": request.document(),
        "summary": result.summary,
        "results": [entry.document() for entry in result.results],
        "result": {
            "applicable": not result.blocked,
            "warnings_require_acknowledgement": result.warnings > 0,
        },
    }
