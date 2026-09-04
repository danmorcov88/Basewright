"""Running the rules, and deciding what a run of them came to.

Two kinds of rule arrive here and leave indistinguishable. The shared ones ask their
question in Python because they have to report an observed value against a required one;
the ones a profile contributes ask it as an expression. Both produce a verdict, both have
a severity written beside them, and the resolution of the two is the same four lines for
either -- which is the point, because a report that treated them differently would invite
a profile author to think their rules mattered less.

Nothing here can be overridden. There is no argument that demotes a block, and the only
way to change what refuses a host is to change a rule where a reviewer sees the diff.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

from basewright.expressions import Expression, ExpressionError, Unreported
from basewright.facts.model import HostFacts
from basewright.layout import resolve_paths
from basewright.preflight.model import (
    GateResult,
    PreflightResult,
    Severity,
    Source,
    Verdict,
)
from basewright.preflight.shared import SHARED_RULES, Context, SharedRule
from basewright.profiles.model import GateRule, Profile
from basewright.request import Request, supported_version
from basewright.scope import build_scope


class RuleError(ValueError):
    """A rule that cannot be evaluated because it is written wrongly.

    Distinct from a host that falls short and from a fact nobody collected. This is a
    defect in the profile, and it is refused rather than reported as a verdict: a broken
    rule that quietly skipped would be a gate nobody notices has stopped guarding.
    """

    def __init__(self, rule: GateRule, field: str, source: str, detail: str) -> None:
        self.rule = rule
        self.field = field
        self.detail = detail
        super().__init__(
            f"{rule.identifier}: {detail}\n"
            f"  in requirements.yml, the {field} of this rule: {source!r}"
        )


def evaluate(
    facts: HostFacts,
    profile: Profile,
    request: Request,
    *,
    today: date | None = None,
    now: datetime | None = None,
) -> PreflightResult:
    """Evaluate every rule, shared and contributed, against one host.

    ``today`` is an argument because one rule reads the calendar, and a rule that reads
    the calendar has to be pinnable for a test and for a golden plan to mean anything.
    """
    moment = now or datetime.now(UTC)
    context = Context(
        facts=facts,
        profile=profile,
        request=request,
        paths=resolve_paths(profile, request),
        version=supported_version(profile, request),
        today=today or moment.date(),
    )
    scope = build_scope(facts, profile, request, context.paths)

    results = [
        *(_shared(rule, context) for rule in SHARED_RULES),
        *_contributed(profile, scope),
    ]

    return PreflightResult.of(
        results,
        host=request.host,
        engine=profile.engine,
        profile_version=profile.profile_version,
        version=request.version,
        instance=request.instance,
        evaluated_at=moment,
    )


def _shared(rule: SharedRule, context: Context) -> GateResult:
    """Ask one engine-independent rule what it makes of the host."""
    verdict = rule.check(context)
    return _resolve(
        identifier=rule.identifier,
        source=Source.SHARED,
        severity=rule.severity,
        title=rule.title,
        verdict=verdict,
    )


def _contributed(profile: Profile, scope: dict[str, object]) -> Iterator[GateResult]:
    """Ask each rule the profile added, in the order the profile wrote them."""
    for rule in profile.gates:
        yield _resolve(
            identifier=rule.identifier,
            source=Source.PROFILE,
            severity=Severity(rule.severity),
            title=rule.title,
            verdict=_evaluate_rule(rule, scope),
        )


def _evaluate_rule(rule: GateRule, scope: dict[str, object]) -> Verdict:
    """Work out what one written rule says about the scope.

    Three things can happen and they are three different answers. The rule may not apply,
    which skips. It may read a fact nobody collected, which also skips, and says which
    fact. Or it may be written wrongly, which is not an answer about the host at all and
    stops the run.
    """
    if rule.applies_to is not None:
        applicable = _parse(rule, "applies_to", rule.applies_to)
        try:
            applies = applicable.truth(scope)
        except Unreported as unreported:
            return Verdict.undecidable(
                f"whether this applies depends on {unreported.name}, which was not reported",
                rule.remediation,
            )
        except ExpressionError as error:
            raise RuleError(rule, "applies_to", rule.applies_to, str(error)) from error
        if not applies:
            return Verdict.undecidable("does not apply to this host", rule.remediation)

    condition = _parse(rule, "expr", rule.expr)
    try:
        met = condition.truth(scope)
    except Unreported as unreported:
        return Verdict.undecidable(
            f"{unreported.name} was not reported by this host", rule.remediation
        )
    except ExpressionError as error:
        raise RuleError(rule, "expr", rule.expr, str(error)) from error

    if met:
        return Verdict.satisfied(f"{rule.expr} holds on this host")
    return Verdict.unmet(f"{rule.expr} does not hold on this host", rule.remediation)


def _parse(rule: GateRule, field: str, source: str) -> Expression:
    """Read one of a rule's two expressions, saying which one could not be read."""
    try:
        return Expression.parse(source)
    except ExpressionError as error:
        raise RuleError(rule, field, source, str(error)) from error


def _resolve(
    *,
    identifier: str,
    source: Source,
    severity: Severity,
    title: str,
    verdict: Verdict,
) -> GateResult:
    """Apply a rule's severity to what it found. The whole of severity resolution."""
    return GateResult(
        identifier=identifier,
        source=source,
        severity=severity,
        outcome=verdict.outcome(severity),
        title=title,
        observed=verdict.observed,
        remediation=verdict.remediation,
    )
