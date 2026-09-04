"""Sizing: what order the rules run in, and what happens around the arithmetic.

The arithmetic itself is tested in ``test_expressions.py``. What is tested here is
everything the planner puts around it, which is where a sizing mistake actually comes
from: a value computed before the parameter it depends on, a bound in the wrong unit, a
rounding applied after a floor and landing back underneath it, and a fact nobody
collected turning into a plan with a hole in it.
"""

from __future__ import annotations

from typing import Any

import pytest

from basewright.expressions import UNREPORTED, base_scope
from basewright.planner.sizing import (
    SizingError,
    UnsizedParameterError,
    evaluate,
    evaluation_order,
)
from basewright.profiles.model import SizingRule

WHY = "A reason long enough to be a reason, which the schema insists on and so does review."


def rule(
    parameter: str,
    expr: str,
    *,
    unit: str = "count",
    minimum: str | float | None = None,
    maximum: str | float | None = None,
    warn_above: str | float | None = None,
    round_to: str | float | None = None,
) -> SizingRule:
    return SizingRule(
        identifier=f"fixture.{parameter}",
        parameter=parameter,
        expr=expr,
        why=WHY,
        unit=unit,
        minimum=minimum,
        maximum=maximum,
        warn_above=warn_above,
        round_to=round_to,
    )


def scope(**facts: Any) -> dict[str, Any]:
    """The vocabulary an expression reads, with only what a test needs in it."""
    values = base_scope()
    values["host"] = {"memory": {"total_bytes": 32 * 1024**3}, "cpu": {"cores": 8}, **facts}
    return values


def sized(rules: list[SizingRule], **facts: Any) -> dict[str, Any]:
    return {result.parameter: result for result in evaluate(rules, scope(**facts))}


# --------------------------------------------------------------------------- ordering


def test_a_rule_is_evaluated_after_the_parameter_it_reads() -> None:
    """The file order is deliberately wrong here, and the answer is deliberately right."""
    rules = [rule("derived", "base * 2"), rule("base", "21")]

    results = sized(rules)

    assert results["derived"].value == 42


def test_the_artifact_keeps_the_order_the_profile_wrote() -> None:
    """Evaluation order comes from what the rules read; reading order comes from a person."""
    rules = [rule("derived", "base * 2"), rule("base", "21")]

    assert [result.parameter for result in evaluate(rules, scope())] == ["derived", "base"]


def test_rules_that_read_nothing_of_each_other_keep_their_order() -> None:
    rules = [rule("a", "1"), rule("b", "2"), rule("c", "3")]

    assert [entry.parameter for entry in evaluation_order(rules)] == ["a", "b", "c"]


def test_a_chain_is_resolved_in_full() -> None:
    rules = [rule("third", "second + 1"), rule("second", "first + 1"), rule("first", "1")]

    results = sized(rules)

    assert (results["first"].value, results["second"].value, results["third"].value) == (1, 2, 3)


def test_two_rules_that_need_each_other_are_refused_by_name() -> None:
    """A ring is a defect in the profile, not a loop for the planner to discover slowly."""
    rules = [rule("a", "b + 1"), rule("b", "a + 1")]

    with pytest.raises(SizingError, match="a -> b -> a"):
        evaluation_order(rules)


def test_a_longer_ring_names_every_link() -> None:
    rules = [rule("a", "c + 1"), rule("b", "a + 1"), rule("c", "b + 1")]

    with pytest.raises(SizingError) as raised:
        evaluation_order(rules)

    assert "a -> c -> b -> a" in str(raised.value)


def test_a_rule_that_reads_itself_is_refused() -> None:
    with pytest.raises(SizingError, match="which is the parameter it sets"):
        evaluation_order([rule("a", "a + 1")])


def test_a_later_rule_reads_the_bounded_value_not_the_computed_one() -> None:
    """The instance runs with the clamped number, so that is what the next rule divides by."""
    rules = [rule("capped", "100", maximum=10), rule("derived", "capped * 2")]

    results = sized(rules)

    assert results["capped"].value == 10
    assert results["derived"].value == 20


# ------------------------------------------------------------------ bounds and rounding


def test_a_floor_is_reported_when_it_moved_the_value() -> None:
    result = sized([rule("small", "1", minimum=10)])["small"]

    assert (result.value, result.bounded_by) == (10, "min")


def test_a_ceiling_is_reported_when_it_moved_the_value() -> None:
    result = sized([rule("big", "100", maximum=10)])["big"]

    assert (result.value, result.bounded_by) == (10, "max")


def test_a_value_that_lands_on_its_ceiling_by_arithmetic_is_not_reported_as_bounded() -> None:
    """Held at a ceiling and arriving at one say different things about the machine."""
    result = sized([rule("exact", "10", maximum=10)])["exact"]

    assert (result.value, result.bounded_by) == (10, None)


def test_rounding_happens_before_the_bounds() -> None:
    """The other order can round a value below its own floor, which is the point of one.

    Rounding down after a floor was applied lands under it whenever the floor is not
    itself a multiple, and a parameter below its minimum is one the engine cannot use.
    """
    result = sized([rule("size", "200", unit="bytes", round_to=256, minimum=100)])["size"]

    assert (result.value, result.bounded_by) == (100, "min")


def test_rounding_goes_down_to_a_multiple() -> None:
    result = sized([rule("size", "1000", unit="bytes", round_to=256)])["size"]

    assert result.value == 768


def test_a_min_above_a_max_is_a_defect_in_the_profile() -> None:
    with pytest.raises(SizingError, match="min above its max"):
        sized([rule("impossible", "5", minimum=10, maximum=1)])


def test_rounding_to_zero_is_refused() -> None:
    with pytest.raises(SizingError, match="rounds to zero"):
        sized([rule("size", "10", unit="bytes", round_to=0)])


# ------------------------------------------------------------------------------- units


def test_a_byte_bound_is_read_with_its_unit() -> None:
    result = sized([rule("cache", "0.25 * host.memory.total_bytes", unit="bytes", maximum="1GiB")])

    assert result["cache"].value == 1024**3
    assert result["cache"].display == "1.0 GiB"


def test_binary_and_decimal_bounds_mean_what_they_say() -> None:
    binary = sized([rule("a", "1000000000000", unit="bytes", maximum="1GiB")])["a"]
    decimal = sized([rule("a", "1000000000000", unit="bytes", maximum="1GB")])["a"]

    assert binary.value == 1073741824
    assert decimal.value == 1000000000


def test_a_duration_bound_is_read_in_the_unit_the_parameter_uses() -> None:
    seconds = sized([rule("interval", "1000", unit="seconds", maximum="30s")])["interval"]
    milliseconds = sized([rule("timeout", "9999", unit="milliseconds", maximum="2s")])["timeout"]

    assert seconds.value == 30
    assert milliseconds.value == 2000


def test_a_duration_bound_that_is_not_whole_in_the_parameter_unit_is_refused() -> None:
    with pytest.raises(SizingError, match="whole number of seconds"):
        sized([rule("interval", "1", unit="seconds", maximum="1500ms")])


def test_a_bound_with_a_unit_on_a_parameter_that_has_none_is_refused() -> None:
    """A bound in the wrong unit is off by a factor nobody notices in a review."""
    with pytest.raises(SizingError, match="carries no unit"):
        sized([rule("connections", "200", unit="count", maximum="8GiB")])


def test_a_quantity_is_rendered_the_way_a_person_reads_it() -> None:
    results = sized(
        [
            rule("size", "8589934592", unit="bytes"),
            rule("interval", "300", unit="seconds"),
            rule("timeout", "250", unit="milliseconds"),
            rule("cost", "1.1", unit="ratio"),
            rule("pages", "'try'", unit="text"),
        ]
    )

    assert results["size"].display == "8.0 GiB"
    assert results["interval"].display == "300 s"
    assert results["timeout"].display == "250 ms"
    assert results["cost"].display == "1.1"
    assert results["pages"].display == "try"


def test_a_counted_unit_is_a_whole_number() -> None:
    """Rounded down, never to nearest: half a byte promised is a promise not kept."""
    result = sized([rule("size", "10 / 3", unit="bytes")])["size"]

    assert result.value == 3


def test_a_ratio_keeps_its_fraction() -> None:
    result = sized([rule("cost", "1.1", unit="ratio")])["cost"]

    assert result.value == pytest.approx(1.1)


# ------------------------------------------------------------------------------- text


def test_a_text_parameter_carries_the_word() -> None:
    expr = "'try' if host.memory.total_bytes >= 32 * GiB else 'off'"
    result = sized([rule("pages", expr, unit="text")])

    assert result["pages"].value == "try"


def test_a_bound_on_a_text_parameter_is_refused() -> None:
    with pytest.raises(SizingError, match="no use for"):
        sized([rule("pages", "'try'", unit="text", maximum=4)])


def test_a_text_rule_that_produces_a_number_is_refused() -> None:
    with pytest.raises(SizingError, match="measured in text"):
        sized([rule("pages", "4", unit="text")])


def test_a_numeric_rule_that_produces_text_is_refused() -> None:
    with pytest.raises(SizingError, match="not a number"):
        sized([rule("size", "'large'", unit="bytes")])


# -------------------------------------------------------------------------- advisories


def test_a_value_past_its_advisory_carries_the_threshold_it_passed() -> None:
    result = sized([rule("workers", "64", warn_above=16)])["workers"]

    assert result.above_advisory == 16
    assert result.advised_against


def test_a_value_inside_its_advisory_says_nothing() -> None:
    result = sized([rule("workers", "8", warn_above=16)])["workers"]

    assert result.above_advisory is None
    assert not result.advised_against


def test_an_advisory_does_not_clamp() -> None:
    """It is permitted, and said out loud. Clamping would make it a maximum in disguise."""
    result = sized([rule("workers", "64", warn_above=16)])["workers"]

    assert result.value == 64


def test_the_advisory_is_compared_against_the_value_after_bounds() -> None:
    result = sized([rule("workers", "64", maximum=8, warn_above=16)])["workers"]

    assert result.value == 8
    assert result.above_advisory is None


# ------------------------------------------------------------ what nobody could answer


def test_a_fact_the_host_did_not_report_refuses_the_plan() -> None:
    """Not a defect in the profile and not a host that fell short: nobody can tell."""
    values = scope()
    values["path"] = {"data": {"rotational": UNREPORTED}}

    with pytest.raises(UnsizedParameterError) as raised:
        evaluate([rule("cost", "1.1 if not path.data.rotational else 4.0", unit="ratio")], values)

    assert "path.data.rotational was not reported" in str(raised.value)
    assert "not produced with a value missing" in str(raised.value)


def test_a_misspelled_fact_is_a_defect_rather_than_a_missing_one() -> None:
    """The two are fixed by different people, so they are never reported as the same thing."""
    with pytest.raises(SizingError) as raised:
        sized([rule("size", "host.memory.totl_bytes", unit="bytes")])

    assert not isinstance(raised.value, UnsizedParameterError)


def test_an_unreadable_expression_names_the_rule_and_quotes_it() -> None:
    with pytest.raises(SizingError) as raised:
        sized([rule("size", "max(1, 2)", unit="bytes")])

    assert "fixture.size" in str(raised.value)
    assert "'max(1, 2)'" in str(raised.value)


# ---------------------------------------------------------------------------- document


def test_the_document_carries_the_rule_and_its_reasoning() -> None:
    """A number without a reason is the situation this project exists to end."""
    document = sized([rule("size", "8589934592", unit="bytes")])["size"].document()

    assert document == {
        "parameter": "size",
        "value": 8589934592,
        "unit": "bytes",
        "display": "8.0 GiB",
        "rule": "fixture.size",
        "why": WHY,
    }


def test_the_document_says_when_a_bound_or_an_advisory_was_reached() -> None:
    document = sized([rule("workers", "64", maximum=32, warn_above=16)])["workers"].document()

    assert document["bounded_by"] == "max"
    assert document["above_advisory"] == 16
