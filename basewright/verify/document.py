"""The machine-readable half of a verify run.

Section 10 of the brief asks for a report in the same two forms as the plan. This is the
one Semaphore keeps and a later run diffs against: it carries the plan's identity, the
moment the instance was read, and every check with its outcome, so that a reader a year
later needs neither the plan nor the observation to understand what was decided.

Assembled here rather than in the reporter, for the same reason the preflight document is:
one of the two renderings is read by a person and the other by a machine, and a function
that produced both would end up serving whichever was easier to change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from basewright import __version__
from basewright.verify.run import CheckResult, VerifyResult

#: The version of the contract in ``schema/verification.schema.json``.
SCHEMA_VERSION = "1"


def document(result: VerifyResult, *, verified_at: datetime | None = None) -> dict[str, Any]:
    """The verify report, as the artifact ``--json`` writes."""
    moment = verified_at or datetime.now(UTC)
    return {
        "schema_version": SCHEMA_VERSION,
        "verified_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_version": __version__,
        "plan_id": result.plan_id,
        "host": result.host,
        "engine": result.engine,
        "version": result.version,
        "instance": result.instance,
        "observed_at": result.observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": result.summary,
        "results": [_result(entry) for entry in result.results],
        "result": {"verified": result.verified},
    }


def _result(entry: CheckResult) -> dict[str, Any]:
    """One check. Empty strings are left out rather than written as empty strings.

    A reader of this document should be able to tell a check that carried no remediation
    from one whose remediation was blank, and the schema draws that line by absence.
    """
    written: dict[str, Any] = {
        "id": entry.identifier,
        "kind": entry.kind,
        "title": entry.title,
        "outcome": entry.outcome.value,
        "observed": entry.observed,
    }
    for key, value in (
        ("expected", entry.expected),
        ("remediation", entry.remediation),
        ("expression", entry.expression),
    ):
        if value:
            written[key] = value
    return written
