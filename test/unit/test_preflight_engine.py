"""The rules a profile contributes, and what a whole run of rules comes to.

A rule written as an expression has three ways to end that a shared rule does not: it can
not apply, it can read a fact nobody collected, and it can be written wrongly. The first
two are answers about the host and are reported. The third is a defect in the profile and
stops the run, because a broken rule that skipped quietly would be a gate that has stopped
guarding without anybody being told.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from basewright.facts import load_facts
from basewright.facts.model import Memory
from basewright.preflight import Outcome, Severity, Source, evaluate
from basewright.preflight.engine import RuleError
from basewright.preflight.model import PreflightResult, Verdict
from basewright.profiles import load_profile
from basewright.profiles.model import GateRule
from basewright.request import resolve_request

ROOT = Path(__file__).resolve().parents[2]
PROFILE = load_profile(ROOT / "test" / "fixtures" / "profiles" / "exampledb")
TYPICAL = load_facts(ROOT / "test" / "fixtures" / "hosts" / "typical.json")
CROWDED = load_facts(ROOT / "test" / "fixtures" / "hosts" / "crowded.json")
TODAY = date(2026, 9, 4)


def run(facts=TYPICAL, profile=PROFILE, **request):  # type: ignore[no-untyped-def]
    resolved = resolve_request(profile, host=facts.host, environment="production", **request)
    return evaluate(facts, profile, resolved, today=TODAY)


def with_rules(*rules: GateRule):  # type: ignore[no-untyped-def]
    return replace(PROFILE, gates=rules)


def rule(expr: str, *, severity: str = "block", applies_to: str | None = None) -> GateRule:
    return GateRule(
        identifier="exampledb.test",
        severity=severity,
        title="A rule under test",
        expr=expr,
        remediation="Change something.",
        applies_to=applies_to,
    )


def outcome_of(profile, facts=TYPICAL) -> Outcome:  # type: ignore[no-untyped-def]
    result = run(facts, profile)
    return next(e.outcome for e in result.results if e.identifier == "exampledb.test")


# ------------------------------------------------------------- a rule that is written


def test_a_contributed_rule_passes_when_its_expression_holds() -> None:
    assert outcome_of(with_rules(rule("host.cpu.cores >= 2"))) is Outcome.PASS


def test_a_contributed_rule_blocks_when_it_does_not() -> None:
    assert outcome_of(with_rules(rule("host.cpu.cores >= 64"))) is Outcome.BLOCK


def test_a_contributed_rule_warns_when_that_is_its_severity() -> None:
    assert outcome_of(with_rules(rule("host.cpu.cores >= 64", severity="warn"))) is Outcome.WARN


def test_a_contributed_rule_reads_the_request() -> None:
    assert outcome_of(with_rules(rule("request.port > 1024"))) is Outcome.PASS


def test_a_contributed_rule_reads_a_resolved_path() -> None:
    assert outcome_of(with_rules(rule("not path.data.rotational"))) is Outcome.PASS


def test_a_contributed_rule_reads_the_profile() -> None:
    profile = with_rules(rule("request.version == profile.default_version"))
    assert outcome_of(profile) is Outcome.PASS


def test_a_contributed_rule_is_marked_as_the_profiles() -> None:
    """So a reader knows where to go to argue with it."""
    result = run(profile=with_rules(rule("host.cpu.cores >= 2")))
    entry = next(e for e in result.results if e.identifier == "exampledb.test")
    assert entry.source is Source.PROFILE
    assert entry.severity is Severity.BLOCK


def test_a_shared_rule_is_marked_as_shared() -> None:
    result = run()
    entry = next(e for e in result.results if e.identifier == "cpu.min_cores")
    assert entry.source is Source.SHARED


# ------------------------------------------------------------------ applies_to


def test_a_rule_that_does_not_apply_skips() -> None:
    profile = with_rules(rule("host.cpu.cores >= 64", applies_to="host.arch == 'ppc64le'"))
    assert outcome_of(profile) is Outcome.SKIP


def test_a_rule_that_applies_is_evaluated() -> None:
    profile = with_rules(rule("host.cpu.cores >= 64", applies_to="host.arch == 'x86_64'"))
    assert outcome_of(profile) is Outcome.BLOCK


def test_a_rule_whose_applicability_cannot_be_decided_skips() -> None:
    facts = replace(TYPICAL, memory=Memory(total_bytes=34359738368))
    profile = with_rules(rule("host.cpu.cores >= 64", applies_to="host.memory.swap_bytes > 0"))
    assert outcome_of(profile, facts) is Outcome.SKIP


def test_the_fixture_rule_with_applies_to_works_both_ways() -> None:
    """exampledb.storage.rotational asks only about hosts that reported the answer."""
    result = run()
    entry = next(e for e in result.results if e.identifier == "exampledb.storage.rotational")
    assert entry.outcome is Outcome.PASS

    result = run(CROWDED)
    entry = next(e for e in result.results if e.identifier == "exampledb.storage.rotational")
    assert entry.outcome is Outcome.WARN


def test_the_fixture_rule_skips_where_the_host_did_not_report_rotation() -> None:
    mounts = tuple(replace(entry, rotational=None) for entry in TYPICAL.mounts)
    result = run(replace(TYPICAL, mounts=mounts))
    entry = next(e for e in result.results if e.identifier == "exampledb.storage.rotational")
    assert entry.outcome is Outcome.SKIP


# ---------------------------------------------------------------- unreported facts


def test_a_rule_reading_an_uncollected_fact_skips_and_names_it() -> None:
    facts = replace(TYPICAL, memory=Memory(total_bytes=34359738368))
    result = run(facts, with_rules(rule("host.memory.swap_bytes > 0")))
    entry = next(e for e in result.results if e.identifier == "exampledb.test")
    assert entry.outcome is Outcome.SKIP
    assert "host.memory.swap_bytes" in entry.observed


def test_a_skipped_rule_still_carries_its_remedy() -> None:
    facts = replace(TYPICAL, memory=Memory(total_bytes=34359738368))
    result = run(facts, with_rules(rule("host.memory.swap_bytes > 0")))
    entry = next(e for e in result.results if e.identifier == "exampledb.test")
    assert entry.remediation == "Change something."


# ------------------------------------------------------------------ a broken rule


def test_a_misspelled_fact_stops_the_run() -> None:
    """It is not a skip. A typo that skipped would be a gate nobody knows has stopped."""
    with pytest.raises(RuleError, match="not something this reads"):
        run(profile=with_rules(rule("host.memroy.total_bytes > 0")))


def test_a_rule_that_is_not_an_expression_stops_the_run() -> None:
    with pytest.raises(RuleError, match="not a readable expression"):
        run(profile=with_rules(rule("host.cpu.cores >")))


def test_a_rule_that_calls_something_stops_the_run() -> None:
    with pytest.raises(RuleError, match="a function call"):
        run(profile=with_rules(rule("len(host.locales) > 0")))


def test_a_rule_that_returns_a_number_stops_the_run() -> None:
    with pytest.raises(RuleError, match="not a yes or a no"):
        run(profile=with_rules(rule("host.cpu.cores")))


def test_a_broken_applies_to_stops_the_run_and_says_which_field_it_was() -> None:
    with pytest.raises(RuleError) as raised:
        run(profile=with_rules(rule("host.cpu.cores > 1", applies_to="len(host)")))
    assert raised.value.field == "applies_to"
    assert "len(host)" in str(raised.value)


def test_a_rule_error_names_the_rule_and_quotes_the_expression() -> None:
    with pytest.raises(RuleError) as raised:
        run(profile=with_rules(rule("host.memroy.total_bytes > 0")))
    assert "exampledb.test" in str(raised.value)
    assert "host.memroy.total_bytes > 0" in str(raised.value)
    assert raised.value.field == "expr"


# ---------------------------------------------------------------- the run as a whole


def test_a_clean_host_is_applicable() -> None:
    result = run()
    assert not result.blocked
    assert result.summary["block"] == 0


def test_a_blocked_host_is_not() -> None:
    result = run(CROWDED)
    assert result.blocked
    assert result.summary["block"] > 0


def test_the_counts_add_up_to_every_rule() -> None:
    result = run(CROWDED)
    assert sum(result.summary.values()) == len(result.results)


def test_results_are_ordered_blocks_first_then_by_identifier() -> None:
    """Two runs of the same inputs have to read the same way, and the same way round."""
    result = run(CROWDED)
    order = [(entry.outcome, entry.identifier) for entry in result.results]
    ranking = {Outcome.BLOCK: 0, Outcome.WARN: 1, Outcome.SKIP: 2, Outcome.PASS: 3}
    assert order == sorted(order, key=lambda pair: (ranking[pair[0]], pair[1]))


def test_evaluation_is_deterministic() -> None:
    moment = datetime(2026, 9, 4, 10, 14, 22, tzinfo=UTC)
    resolved = resolve_request(PROFILE, host=CROWDED.host, environment="production")
    first = evaluate(CROWDED, PROFILE, resolved, today=TODAY, now=moment)
    second = evaluate(CROWDED, PROFILE, resolved, today=TODAY, now=moment)
    assert first == second


def test_today_defaults_to_the_moment_of_the_run() -> None:
    moment = datetime(2027, 1, 1, 0, 0, 0, tzinfo=UTC)
    resolved = resolve_request(PROFILE, host=TYPICAL.host, environment="production")
    result = evaluate(TYPICAL, PROFILE, resolved, now=moment)
    assert result.evaluated_at == moment


def test_a_verdict_resolves_against_its_severity() -> None:
    unmet = Verdict.unmet("something", "change it")
    assert unmet.outcome(Severity.BLOCK) is Outcome.BLOCK
    assert unmet.outcome(Severity.WARN) is Outcome.WARN
    assert Verdict.satisfied("fine").outcome(Severity.BLOCK) is Outcome.PASS
    assert Verdict.undecidable("nobody asked").outcome(Severity.BLOCK) is Outcome.SKIP


def test_a_result_with_nothing_in_it_is_not_blocked() -> None:
    empty = PreflightResult.of(
        [],
        host="db.invalid",
        engine="exampledb",
        profile_version="1.0.0",
        version="3",
        instance="main",
        evaluated_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    assert not empty.blocked
    assert empty.summary == {"pass": 0, "warn": 0, "block": 0, "skip": 0}
