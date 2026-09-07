"""Putting a profile's checks to one observation, and what the whole run came to.

The shape of this is the gate engine's, deliberately: a list of declared checks, one
judgement each, one resolution at the end, and no argument anywhere that changes it. What
is different is what a failure means. A gate refuses a host before anything has been done
to it, and there is a way out -- change the machine, or change the request. A verify
failure is about a machine that has already been changed, so what it says is that the
artifact somebody approved is no longer a description of what is running, and the way out
is to find out why.

There is no severity here and there will not be. A profile's verify checks are all the
same weight, because they are all statements the plan already made: an instance that does
not match the plan in one respect is not matching the plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from basewright.expressions import Expression, ExpressionError, Unreported
from basewright.profiles.model import Profile, VerifyCheck
from basewright.verify.judge import JUDGEMENTS
from basewright.verify.model import Observation, Outcome
from basewright.verify.scope import build_verification_scope


class VerifyError(Exception):
    """The run cannot proceed at all, so there is nothing to report check by check.

    Kept apart from a check that failed, because they are answers to different questions.
    A failing check says the instance is wrong; this says the two documents being compared
    are not about the same instance, and comparing them would produce a verdict rather than
    a mistake.
    """


@dataclass(frozen=True)
class CheckResult:
    """One check: what was asked, what came back, and what that came to."""

    identifier: str
    kind: str
    title: str
    outcome: Outcome
    observed: str
    expected: str = ""
    remediation: str = ""
    expression: str = ""


@dataclass(frozen=True)
class VerifyResult:
    """A whole run of checks against one instance."""

    host: str
    engine: str
    version: str
    instance: str
    plan_id: str
    observed_at: datetime
    results: tuple[CheckResult, ...]

    @property
    def verified(self) -> bool:
        """Whether the instance is the one the plan describes.

        Every check has to pass. A check nobody managed to run leaves this false, because
        the claim being made is that the instance was proved to match, and an unasked
        question proves nothing (ADR-0025).
        """
        return all(entry.outcome.verified for entry in self.results)

    @property
    def summary(self) -> dict[str, int]:
        """How many checks came to each outcome."""
        return {
            outcome.value: sum(1 for entry in self.results if entry.outcome is outcome)
            for outcome in Outcome
        }

    def counting(self, outcome: Outcome) -> int:
        """How many checks came to one outcome."""
        return sum(1 for entry in self.results if entry.outcome is outcome)


def verify(
    plan: dict[str, Any],
    profile: Profile,
    observation: Observation,
) -> VerifyResult:
    """Judge one instance against the plan it came from.

    Refuses outright, rather than reporting check by check, when the observation is not of
    this plan. That is not pedantry about identifiers: a plan is named after a digest of
    its own content, so an observation carrying a different one was taken against different
    promises, and every line of the report that followed would be a comparison of two
    unrelated things presented as a verdict.
    """
    if observation.plan_id != plan["plan_id"]:
        raise VerifyError(
            f"this observation was taken against plan {observation.plan_id}, and the plan "
            f"given is {plan['plan_id']}. A plan is named after a digest of its own "
            f"content, so these are two different sets of promises. Verify the instance "
            f"against the plan it was built from."
        )

    host = plan["request"]["host"]
    if observation.host != host:
        raise VerifyError(
            f"this observation was taken on {observation.host}, and the plan describes "
            f"{host}. Reading one machine and reporting it against another machine's plan "
            f"would produce a verdict about neither."
        )

    scope = build_verification_scope(plan, observation)
    results = tuple(_check(entry, plan, observation, scope) for entry in profile.checks)

    return VerifyResult(
        host=host,
        engine=plan["request"]["engine"],
        version=plan["request"]["version"],
        instance=plan["request"]["instance"],
        plan_id=plan["plan_id"],
        observed_at=observation.observed_at,
        results=results,
    )


def _check(
    entry: VerifyCheck,
    plan: dict[str, Any],
    observation: Observation,
    scope: dict[str, Any],
) -> CheckResult:
    """One check: the kind's judgement first, then the profile's expression over it."""
    reading = observation.of(entry.kind)
    if reading is None:
        return _result(
            entry,
            Outcome.UNOBSERVED,
            f"the run took no {entry.kind} reading from this instance",
        )

    outcome, observed, expected = JUDGEMENTS[entry.kind](plan, reading)
    if outcome is not Outcome.PASS or entry.expr is None:
        return _result(entry, outcome, observed, expected)

    return _narrowed(entry, observed, expected, scope)


def _narrowed(
    entry: VerifyCheck,
    observed: str,
    expected: str,
    scope: dict[str, Any],
) -> CheckResult:
    """A check whose kind is satisfied and whose profile asks for more.

    The expression is a narrowing and never a widening: it is evaluated only on a kind that
    already passed, so a profile cannot write one that excuses a mismatch. What it can do is
    refuse something the kind has no opinion about, which is the whole reason it exists.
    """
    expression = Expression.parse(entry.expr or "")
    try:
        met = expression.truth(scope)
    except Unreported:
        return _result(
            entry,
            Outcome.UNOBSERVED,
            f"{observed}; the profile's own condition reads something this run did not observe",
            expected,
        )
    except ExpressionError as error:
        # A misspelling in a profile, not an instance that fell short. Loud, and named at
        # the column, because the person who has to fix it is editing that file.
        raise VerifyError(
            f"{entry.identifier}: the profile's condition cannot be read -- {error}"
        ) from error

    if met:
        return _result(entry, Outcome.PASS, observed, expected)
    return _result(
        entry,
        Outcome.FAIL,
        f"{observed}; the profile's own condition is not met",
        expected,
    )


def _result(
    entry: VerifyCheck,
    outcome: Outcome,
    observed: str,
    expected: str = "",
) -> CheckResult:
    """Attach what the profile wrote to what the judgement found."""
    return CheckResult(
        identifier=entry.identifier,
        kind=entry.kind,
        title=entry.title,
        outcome=outcome,
        observed=observed,
        expected=expected,
        remediation="" if outcome is Outcome.PASS else entry.remediation,
        expression=entry.expr or "",
    )
