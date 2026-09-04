"""The expression language: what it reads, what it refuses, and how it says so.

The refusals matter as much as the evaluations here. This is the one place in the project
where text from a file becomes an answer, so every construct that could turn text into
behaviour has a test proving it is rejected at parse time rather than at run time.
"""

from __future__ import annotations

import pytest

from basewright.expressions import (
    UNREPORTED,
    Expression,
    ExpressionError,
    Unreported,
    base_scope,
)


def scope(**extra: object) -> dict[str, object]:
    """A vocabulary with the units and a small host in it."""
    built = base_scope()
    built["host"] = {
        "arch": "x86_64",
        "cpu": {"cores": 8},
        "memory": {"total_bytes": 34359738368, "swap_bytes": UNREPORTED},
        "locales": ("C.UTF-8", "en_US.UTF-8"),
        "rotational": None,
    }
    built["max_connections"] = 200
    built.update(extra)
    return built


def evaluate(source: str, **extra: object) -> object:
    return Expression.parse(source).evaluate(scope(**extra))


# ------------------------------------------------------------------ what it reads


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("1", 1),
        ("1.5", 1.5),
        ("'text'", "text"),
        ("True", True),
        ("none", None),
        ("host.cpu.cores", 8),
        ("host.cpu.cores + 2", 10),
        ("host.cpu.cores - 2", 6),
        ("host.cpu.cores * 2", 16),
        ("host.cpu.cores / 2", 4.0),
        ("host.cpu.cores // 3", 2),
        ("host.cpu.cores % 3", 2),
        ("-host.cpu.cores", -8),
        ("+host.cpu.cores", 8),
        ("2 * GiB", 2147483648),
        ("2 * GB", 2000000000),
        ("host.memory.total_bytes >= 2 * GiB", True),
        ("host.memory.total_bytes < 2 * GiB", False),
        ("host.cpu.cores == 8", True),
        ("host.cpu.cores != 8", False),
        ("host.cpu.cores <= 8", True),
        ("host.cpu.cores > 8", False),
        ("2 < host.cpu.cores < 16", True),
        ("2 < host.cpu.cores < 4", False),
        ("host.arch == 'x86_64' and host.cpu.cores > 4", True),
        ("host.arch == 'ppc64le' or host.cpu.cores > 4", True),
        ("host.arch == 'ppc64le' and host.cpu.cores > 4", False),
        ("not host.cpu.cores > 100", True),
        ("host.rotational is none", True),
        ("host.rotational is not none", False),
        ("'en_US.UTF-8' in host.locales", True),
        ("'de_DE.UTF-8' in host.locales", False),
        ("'de_DE.UTF-8' not in host.locales", True),
        ("host.arch in ('x86_64', 'aarch64')", True),
        ("host.arch in ['ppc64le']", False),
        ("1.1 if host.cpu.cores > 4 else 4.0", 1.1),
        ("1.1 if host.cpu.cores > 40 else 4.0", 4.0),
        ("(0.25 * host.memory.total_bytes) / (max_connections * 2)", 21474836.48),
        ("'x' < 'y'", True),
    ],
)
def test_reads(source: str, expected: object) -> None:
    assert evaluate(source) == expected


def test_boolean_operators_answer_with_a_yes_or_a_no() -> None:
    """Not with the last operand, which is what Python would hand back.

    A rule that reported a number as its verdict would be resolved against a severity and
    reported as a pass, which is a gate that has silently stopped asking anything.
    """
    assert evaluate("host.cpu.cores > 4 and host.cpu.cores > 2") is True
    assert evaluate("host.cpu.cores > 40 or host.cpu.cores > 400") is False


def test_whitespace_around_an_expression_is_not_part_of_it() -> None:
    assert Expression.parse("  host.cpu.cores > 2  ").source == "host.cpu.cores > 2"


def test_names_reports_what_a_rule_depends_on() -> None:
    assert Expression.parse("host.cpu.cores > 2 * GiB").names() == frozenset({"host", "GiB"})


def test_truth_insists_on_a_yes_or_a_no() -> None:
    expression = Expression.parse("host.cpu.cores")
    with pytest.raises(ExpressionError, match="not a yes or a no"):
        expression.truth(scope())


def test_truth_accepts_a_comparison() -> None:
    assert Expression.parse("host.cpu.cores > 2").truth(scope()) is True


# --------------------------------------------------------------- what it refuses


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("len(host.locales)", "a function call"),
        ("host.locales[0]", "a subscript"),
        ("lambda: 1", "a lambda"),
        ("[x for x in host.locales]", "a comprehension"),
        ("{x for x in host.locales}", "a comprehension"),
        ("{x: 1 for x in host.locales}", "a comprehension"),
        ("(x for x in host.locales)", "a generator"),
        ("f'{host}'", "a formatted string"),
        ("{'a': 1}", "a dict literal"),
        ("{'a'}", "a set literal"),
        ("host.cpu.cores ** 2", "not an operator this language has"),
        ("host.__class__", "not a name this language reads"),
        ("_secret", "not a name this language reads"),
        ("host.cpu.cores & 1", "not an operator this language has"),
        ("~host.cpu.cores", "not an operator this language has"),
    ],
)
def test_refuses_at_parse_time(source: str, expected: str) -> None:
    with pytest.raises(ExpressionError, match=expected):
        Expression.parse(source)


def test_a_refusal_names_the_column() -> None:
    """So that a profile author fixes it in one edit rather than by bisection."""
    with pytest.raises(ExpressionError) as raised:
        Expression.parse("host.cpu.cores > len(host.locales)")
    assert raised.value.column == 17
    assert "column 17" in str(raised.value)


def test_refuses_something_that_is_not_an_expression_at_all() -> None:
    with pytest.raises(ExpressionError, match="not a readable expression"):
        Expression.parse("host.cpu.cores >")


def test_refuses_a_name_the_scope_does_not_define() -> None:
    """A misspelled fact is a defect in the profile, and must not pass for a missing one."""
    with pytest.raises(ExpressionError, match="not something this reads"):
        evaluate("host.memroy.total_bytes")


def test_a_missing_name_lists_what_is_available() -> None:
    with pytest.raises(ExpressionError, match="cpu, locales, memory, rotational"):
        evaluate("host.memroy")


def test_refuses_an_attribute_of_something_that_has_none() -> None:
    with pytest.raises(ExpressionError, match="has no 'cores'"):
        evaluate("host.arch.cores")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("host.cpu.cores / 0", "has no answer"),
        ("host.cpu.cores // 0", "has no answer"),
        ("host.cpu.cores % 0", "has no answer"),
        ("host.arch * 2", "not a number"),
        ("host.arch > 2", "no order between them"),
        ("True > 2", "orders a yes or a no"),
        ("'a' in host.cpu", "which nothing can be in"),
        ("host.cpu and True", "not a yes or a no"),
        ("not host.cpu.cores", "not a yes or a no"),
        ("1 if host.cpu.cores else 2", "not a yes or a no"),
    ],
)
def test_refuses_at_evaluation(source: str, expected: str) -> None:
    with pytest.raises(ExpressionError, match=expected):
        evaluate(source)


# --------------------------------------------------------- what nobody can answer


def test_an_unreported_fact_is_not_an_error() -> None:
    with pytest.raises(Unreported) as raised:
        evaluate("host.memory.swap_bytes > 0")
    assert raised.value.name == "host.memory.swap_bytes"
    assert "was not reported" in str(raised.value)


def test_an_unreported_fact_at_the_top_level_is_named_too() -> None:
    with pytest.raises(Unreported, match="firewall"):
        evaluate("firewall == 1", firewall=UNREPORTED)


def test_short_circuiting_does_not_reach_an_unreported_fact() -> None:
    """A rule that has already been decided does not need the fact it did not read."""
    assert evaluate("host.cpu.cores > 100 and host.memory.swap_bytes > 0") is False
    assert evaluate("host.cpu.cores > 1 or host.memory.swap_bytes > 0") is True


def test_a_branch_not_taken_does_not_reach_an_unreported_fact() -> None:
    assert evaluate("1 if host.cpu.cores > 4 else host.memory.swap_bytes") == 1


def test_an_expression_renders_as_it_was_written() -> None:
    assert str(Expression.parse("host.cpu.cores >= 2")) == "host.cpu.cores >= 2"
