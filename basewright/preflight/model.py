"""What a rule decided, and what a whole run of them came to.

Four outcomes, and the fourth is the one that is easy to leave out. A rule that could not
be evaluated -- because the fact it reads was not collected, or because it does not apply
to this host -- reports ``skip``. Folding that into a pass would mean a run reporting
twenty agreements when three of them were silence, and silence is what a refusal is for.

Severity and outcome are separate on purpose. A rule's severity is written in the profile
or, for the shared rules, in the source; its outcome is what happened on one host. The
mapping between them is the whole of the severity resolution, it is four lines long, and
there is no argument anywhere that changes it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    """What one rule did on one host."""

    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
    SKIP = "skip"

    @property
    def stops_the_run(self) -> bool:
        return self is Outcome.BLOCK


class Severity(StrEnum):
    """How badly a rule matters. There are two, and there is no third."""

    BLOCK = "block"
    WARN = "warn"

    def outcome_when_unmet(self) -> Outcome:
        """The severity resolution, in one place.

        No flag reaches this. A block that could be demoted at run time would be a block
        nobody has to fix, and the rule would stay wrong in Git where it does the damage.
        """
        return Outcome.BLOCK if self is Severity.BLOCK else Outcome.WARN


class Source(StrEnum):
    """Where a rule came from, which is where someone goes to argue with it."""

    SHARED = "shared"
    PROFILE = "profile"


@dataclass(frozen=True)
class Verdict:
    """What a check found, before its severity is applied.

    A check answers what it saw; it does not decide how much that matters. Keeping the
    two apart is what lets one report render a profile's rules and the shared ones on
    identical terms.
    """

    met: bool | None
    observed: str
    remediation: str = ""

    @classmethod
    def satisfied(cls, observed: str) -> Verdict:
        """The host meets the rule."""
        return cls(met=True, observed=observed)

    @classmethod
    def unmet(cls, observed: str, remediation: str) -> Verdict:
        """The host does not meet the rule, and here is what would change that."""
        return cls(met=False, observed=observed, remediation=remediation)

    @classmethod
    def undecidable(cls, observed: str, remediation: str = "") -> Verdict:
        """Nobody can tell: the fact was not collected, or the rule does not apply."""
        return cls(met=None, observed=observed, remediation=remediation)

    def outcome(self, severity: Severity) -> Outcome:
        if self.met is None:
            return Outcome.SKIP
        return Outcome.PASS if self.met else severity.outcome_when_unmet()


@dataclass(frozen=True)
class GateResult:
    """One rule, and what it made of one host."""

    identifier: str
    source: Source
    severity: Severity
    outcome: Outcome
    title: str
    observed: str
    remediation: str = ""

    def document(self) -> dict[str, Any]:
        """The result as an artifact carries it."""
        document: dict[str, Any] = {
            "id": self.identifier,
            "source": str(self.source),
            "severity": str(self.severity),
            "outcome": str(self.outcome),
            "title": self.title,
            "observed": self.observed,
        }
        if self.remediation and self.outcome is not Outcome.PASS:
            document["remediation"] = self.remediation
        return document


#: The order results are reported in: what stops the run, then what has to be
#: acknowledged, then what nobody could decide, then what agreed.
_ORDER: dict[Outcome, int] = {
    Outcome.BLOCK: 0,
    Outcome.WARN: 1,
    Outcome.SKIP: 2,
    Outcome.PASS: 3,
}


@dataclass(frozen=True)
class PreflightResult:
    """Every rule that was evaluated, and what the run of them came to."""

    host: str
    engine: str
    profile_version: str
    version: str
    instance: str
    evaluated_at: datetime
    results: tuple[GateResult, ...]

    @classmethod
    def of(
        cls,
        results: Sequence[GateResult],
        *,
        host: str,
        engine: str,
        profile_version: str,
        version: str,
        instance: str,
        evaluated_at: datetime,
    ) -> PreflightResult:
        """Order the results once, so that two runs of the same inputs read the same."""
        ordered = sorted(results, key=lambda result: (_ORDER[result.outcome], result.identifier))
        return cls(
            host=host,
            engine=engine,
            profile_version=profile_version,
            version=version,
            instance=instance,
            evaluated_at=evaluated_at,
            results=tuple(ordered),
        )

    def counting(self, outcome: Outcome) -> int:
        return sum(1 for result in self.results if result.outcome is outcome)

    def with_outcome(self, outcome: Outcome) -> tuple[GateResult, ...]:
        return tuple(result for result in self.results if result.outcome is outcome)

    @property
    def blocked(self) -> bool:
        """True when any rule blocked. A blocked host produces a refusal, never a plan."""
        return any(result.outcome.stops_the_run for result in self.results)

    @property
    def warnings(self) -> int:
        return self.counting(Outcome.WARN)

    @property
    def summary(self) -> dict[str, int]:
        return {
            "pass": self.counting(Outcome.PASS),
            "warn": self.counting(Outcome.WARN),
            "block": self.counting(Outcome.BLOCK),
            "skip": self.counting(Outcome.SKIP),
        }
