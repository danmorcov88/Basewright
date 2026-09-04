"""Working out what each tuneable setting should be on one host, and why.

The arithmetic is already somebody else's job: :mod:`basewright.expressions` reads the
formula a profile wrote and evaluates it against the same vocabulary the gate rules use.
What is here is everything around the formula, which is where the mistakes actually live:

* **Order.** A rule may read a parameter another rule sets. So the order values are
  computed in comes from what they read, not from where they sit in the file, and two
  rules that each need the other's answer first are a defect in the profile rather than a
  loop that never ends. The artifact still lists parameters in the order the file wrote
  them, because that is the order a person chose and the order a reviewer reads.

* **Units.** A bound is written the way a person says it -- ``128MiB``, ``30s`` -- and a
  bound whose unit is not the one the parameter is measured in is refused rather than
  quietly taken as a bare number.

* **Rounding, then bounds, in that order.** Rounding down after a floor has been applied
  lands under that floor whenever the floor is not itself a multiple of the step, and a
  parameter below its own minimum is one the engine cannot use. So a bound is the last
  thing applied and it wins: the bound is a requirement and the rounding is a courtesy.

* **What the plan carries.** The value is canonical -- a count of bytes, a number of
  seconds -- because verify reads the running instance back and compares, and comparing
  rendered text against whatever a server chose to print is not a comparison. Rendering
  the value the way a configuration file expects to read it is the template's job, where
  the syntax of one engine belongs. ``display`` exists so that a person, and the diff of
  a golden plan, can read it.

A rule that reads a fact the host did not report does not silently produce no parameter.
It refuses the plan, naming the rule and the fact, because a plan with a hole in it is
one apply discovers halfway through.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from basewright.expressions import Expression, ExpressionError, Unreported
from basewright.planner.errors import PlanError
from basewright.profiles.model import SizingRule
from basewright.units import UnitError, parse_bytes, parse_milliseconds, render_bytes

__all__ = [
    "Sized",
    "SizingError",
    "UnsizedParameterError",
    "evaluate",
    "evaluation_order",
]

#: The units a value can be measured in, and whether it is counted in whole things.
#: Text is the odd one: it has no arithmetic, so it has no bounds and no rounding either.
_WHOLE: frozenset[str] = frozenset({"bytes", "milliseconds", "seconds", "count"})


class SizingError(PlanError):
    """A sizing rule that cannot be evaluated because it is written wrongly.

    Always a defect in the profile. The message names the rule and quotes its expression,
    because it is read by the person editing that file.
    """

    def __init__(self, rule: SizingRule, detail: str) -> None:
        self.rule = rule
        self.detail = detail
        super().__init__(
            f"{rule.identifier}: {detail}\n"
            f"  in sizing.yml, the rule setting {rule.parameter}: {rule.expr!r}"
        )


class UnsizedParameterError(PlanError):
    """A sizing rule that reads a fact this host did not report.

    Not a defect in the profile and not a host that fell short: nobody can tell. There is
    no value to write into the plan, so there is no plan.
    """

    def __init__(self, rule: SizingRule, name: str) -> None:
        self.rule = rule
        self.name = name
        super().__init__(
            f"{rule.identifier}: {name} was not reported by this host, so {rule.parameter} "
            f"cannot be sized.\n"
            f"  in sizing.yml, the rule setting {rule.parameter}: {rule.expr!r}\n"
            f"  Collect the fact, or write a rule that does not depend on it. A plan is "
            f"not produced with a value missing from it."
        )


@dataclass(frozen=True)
class Sized:
    """One parameter, the value it was given, and the rule that gave it."""

    parameter: str
    value: int | float | str
    unit: str
    display: str
    rule: str
    why: str
    bounded_by: str | None = None
    above_advisory: int | float | None = None

    @property
    def advised_against(self) -> bool:
        """Whether the value is permitted but past what the rule wanted said out loud."""
        return self.above_advisory is not None

    def document(self) -> dict[str, Any]:
        """The parameter as the plan carries it."""
        document: dict[str, Any] = {
            "parameter": self.parameter,
            "value": self.value,
            "unit": self.unit,
            "display": self.display,
            "rule": self.rule,
            "why": self.why,
        }
        if self.bounded_by is not None:
            document["bounded_by"] = self.bounded_by
        if self.above_advisory is not None:
            document["above_advisory"] = self.above_advisory
        return document

    def __str__(self) -> str:
        return f"{self.parameter} {self.display}"


def evaluate(rules: Sequence[SizingRule], scope: Mapping[str, Any]) -> tuple[Sized, ...]:
    """Size every parameter, in the order the rules need, and report them in file order.

    The value a later rule reads is the final one -- after rounding and after bounds --
    because that is what the instance will run with. Feeding it the unclamped number
    would size one parameter against a value no machine will ever have.
    """
    working = dict(scope)
    sized: dict[str, Sized] = {}

    for rule in evaluation_order(rules):
        result = _size(rule, working)
        working[rule.parameter] = result.value
        sized[rule.parameter] = result

    return tuple(sized[rule.parameter] for rule in rules)


def evaluation_order(rules: Sequence[SizingRule]) -> tuple[SizingRule, ...]:
    """The order the rules have to be evaluated in for each to have what it reads.

    Ties are broken by the order of the file, so a profile whose rules do not depend on
    one another is evaluated exactly as it is written.
    """
    parsed = {rule.parameter: _parse(rule) for rule in rules}
    declared = {rule.parameter: index for index, rule in enumerate(rules)}

    needs: dict[str, frozenset[str]] = {
        rule.parameter: frozenset(parsed[rule.parameter].names()) & set(declared) - {rule.parameter}
        for rule in rules
    }
    for rule in rules:
        if rule.parameter in parsed[rule.parameter].names():
            raise SizingError(rule, f"reads {rule.parameter}, which is the parameter it sets")

    ordered: list[SizingRule] = []
    settled: set[str] = set()
    remaining = list(rules)

    while remaining:
        ready = [rule for rule in remaining if needs[rule.parameter] <= settled]
        if not ready:
            raise SizingError(remaining[0], _cycle(remaining, needs))
        for rule in ready:
            ordered.append(rule)
            settled.add(rule.parameter)
        remaining = [rule for rule in remaining if rule.parameter not in settled]

    return tuple(ordered)


def _cycle(remaining: Sequence[SizingRule], needs: Mapping[str, frozenset[str]]) -> str:
    """Name the ring of parameters that each wait for the next one.

    Every rule still here is waiting for another one that is also still here, so walking
    the dependencies from any of them arrives back at something already visited, and the
    part of the walk from that point on is the ring.
    """
    waiting = {rule.parameter for rule in remaining}
    walk: list[str] = [remaining[0].parameter]
    while True:
        following = sorted(needs[walk[-1]] & waiting)[0]
        if following in walk:
            ring = [*walk[walk.index(following) :], following]
            return (
                f"needs {' which needs '.join(ring[1:])}, and so on: "
                f"{' -> '.join(ring)}. One of these has to be written without the other."
            )
        walk.append(following)


def _parse(rule: SizingRule) -> Expression:
    try:
        return Expression.parse(rule.expr)
    except ExpressionError as error:
        raise SizingError(rule, error.detail) from error


def _size(rule: SizingRule, scope: Mapping[str, Any]) -> Sized:
    """Evaluate one rule, apply its rounding and its bounds, and render the result."""
    expression = _parse(rule)
    try:
        raw = expression.evaluate(scope)
    except Unreported as unreported:
        raise UnsizedParameterError(rule, unreported.name) from unreported
    except ExpressionError as error:
        raise SizingError(rule, error.detail) from error

    if rule.unit == "text":
        return _text(rule, raw)

    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise SizingError(
            rule,
            f"produced {raw!r}, which is not a number, but {rule.parameter} is measured in "
            f"{rule.unit}",
        )

    value = _rounded(rule, raw)
    value, bounded_by = _bounded(rule, value)
    return Sized(
        parameter=rule.parameter,
        value=value,
        unit=rule.unit,
        display=_display(value, rule.unit),
        rule=rule.identifier,
        why=rule.why,
        bounded_by=bounded_by,
        above_advisory=_advisory(rule, value),
    )


def _text(rule: SizingRule, raw: Any) -> Sized:
    """A parameter that is a word rather than a quantity.

    Nothing can be rounded, bounded or advised against, so a rule that tries is refused
    rather than having the field quietly ignored.
    """
    if not isinstance(raw, str):
        raise SizingError(rule, f"produced {raw!r}, but {rule.parameter} is measured in text")
    for field, bound in (
        ("min", rule.minimum),
        ("max", rule.maximum),
        ("round_to", rule.round_to),
        ("warn_above", rule.warn_above),
    ):
        if bound is not None:
            raise SizingError(
                rule, f"sets {field}, which a parameter measured in text has no use for"
            )
    return Sized(
        parameter=rule.parameter,
        value=raw,
        unit=rule.unit,
        display=raw,
        rule=rule.identifier,
        why=rule.why,
    )


def _rounded(rule: SizingRule, value: int | float) -> int | float:
    """Snap the value down to something a person would have chosen, if asked to."""
    whole = _whole(rule, value)
    if rule.round_to is None:
        return whole

    if rule.unit not in _WHOLE:
        raise SizingError(rule, f"rounds, which a parameter measured in {rule.unit} has no use for")

    step = int(_quantity(rule, rule.round_to, field="round_to"))
    if step <= 0:
        raise SizingError(rule, "rounds to zero, which no value is a multiple of")
    return int(whole) - int(whole) % step


def _bounded(rule: SizingRule, value: int | float) -> tuple[int | float, str | None]:
    """Apply the floor and the ceiling, and say which one was reached.

    Reported only when a bound actually moved the value: a number that landed on its
    ceiling by arithmetic says something different about the host from one that was held
    there.
    """
    floor = None if rule.minimum is None else _quantity(rule, rule.minimum, field="min")
    ceiling = None if rule.maximum is None else _quantity(rule, rule.maximum, field="max")

    if floor is not None and ceiling is not None and floor > ceiling:
        raise SizingError(rule, "has a min above its max, so no value satisfies both")

    if floor is not None and value < floor:
        return _whole(rule, floor), "min"
    if ceiling is not None and value > ceiling:
        return _whole(rule, ceiling), "max"
    return value, None


def _advisory(rule: SizingRule, value: int | float) -> int | float | None:
    """The threshold this value went past, if it went past one.

    A permitted value that is worth saying out loud. It does not clamp, and it is not a
    gate -- preflight finished before this parameter existed -- so it travels with the
    parameter and joins the warnings apply has to have acknowledged.
    """
    if rule.warn_above is None:
        return None
    limit = _quantity(rule, rule.warn_above, field="warn_above")
    return _whole(rule, limit) if value > limit else None


def _quantity(rule: SizingRule, bound: str | float, field: str) -> int | float:
    """Read one bound, in the units the parameter is measured in.

    A bare number is already in those units, which is how a count or a ratio is written.
    A string carries its own unit, and one that does not belong to this parameter is
    refused: a bound in the wrong unit is off by a factor nobody notices in review.
    """
    if isinstance(bound, bool):
        raise SizingError(rule, f"has a {field} of {bound!r}, which is not a quantity")
    if isinstance(bound, int | float):
        return bound

    try:
        if rule.unit == "bytes":
            return parse_bytes(bound)
        if rule.unit in {"milliseconds", "seconds"}:
            milliseconds = parse_milliseconds(bound)
            return milliseconds if rule.unit == "milliseconds" else _seconds(rule, milliseconds)
    except UnitError as error:
        raise SizingError(rule, f"has a {field} that {error}") from error

    raise SizingError(
        rule,
        f"has a {field} of {bound!r}, but {rule.parameter} is measured in {rule.unit}, "
        f"which carries no unit. Write the number on its own.",
    )


def _seconds(rule: SizingRule, milliseconds: int) -> int:
    if milliseconds % 1000:
        raise SizingError(
            rule,
            f"has a bound of {milliseconds}ms, which is not a whole number of seconds. "
            f"Write it in the unit the parameter is measured in.",
        )
    return milliseconds // 1000


def _whole(rule: SizingRule, value: int | float) -> int | float:
    """Round a quantity down to a whole one, where the unit is counted in whole things.

    Down, never to nearest: a size rounded up is a promise the machine may not be able to
    keep, and there is no unit here where half of one means anything.
    """
    return int(value) if rule.unit in _WHOLE else value


def _display(value: int | float, unit: str) -> str:
    """The value as a person reads it, which is also how a golden plan diffs."""
    if unit == "bytes":
        return render_bytes(int(value))
    if unit == "milliseconds":
        return f"{value} ms"
    if unit == "seconds":
        return f"{value} s"
    if unit == "ratio":
        return repr(float(value))
    return str(value)
