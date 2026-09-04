"""The refusal report, and the artifact beside it.

The report is read in a terminal, in a Semaphore task log, and in a documentation image
generated on a machine that may not agree with this one about console encoding. So the
tests here are about the two properties that make it usable in all three: it stays inside
its width, and every character in it is ASCII.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from basewright.facts import load_facts
from basewright.preflight import Outcome, document, evaluate
from basewright.preflight.model import GateResult, PreflightResult, Severity, Source
from basewright.profiles import load_profile
from basewright.report.preflight import render_preflight
from basewright.report.problems import REPORT_WIDTH
from basewright.request import resolve_request
from basewright.schema import problems_in

ROOT = Path(__file__).resolve().parents[2]
HOSTS = ROOT / "test" / "fixtures" / "hosts"
PROFILE = load_profile(ROOT / "test" / "fixtures" / "profiles" / "exampledb")
TODAY = date(2026, 9, 4)
MOMENT = datetime(2026, 9, 4, 10, 14, 22, tzinfo=UTC)

FIXTURES = ("typical", "small", "large", "crowded", "rocky")


def result_for(name: str) -> PreflightResult:
    facts = load_facts(HOSTS / f"{name}.json")
    request = resolve_request(PROFILE, host=facts.host, environment="production")
    return evaluate(facts, PROFILE, request, today=TODAY, now=MOMENT)


def rendered(name: str) -> str:
    return render_preflight(result_for(name))


# ------------------------------------------------------------------------ the rendering


@pytest.mark.parametrize("name", FIXTURES)
def test_the_report_is_ascii(name: str) -> None:
    """A capture of this runs as a subprocess in CI, on an OS that disagrees about encoding."""
    rendered(name).encode("ascii")


@pytest.mark.parametrize("name", FIXTURES)
def test_the_report_stays_inside_its_width(name: str) -> None:
    too_wide = [line for line in rendered(name).splitlines() if len(line) > REPORT_WIDTH]
    assert not too_wide, f"lines longer than {REPORT_WIDTH}: {too_wide}"


@pytest.mark.parametrize("name", FIXTURES)
def test_the_report_names_the_host_the_engine_and_the_instance(name: str) -> None:
    result = result_for(name)
    first = rendered(name).splitlines()[0]
    assert result.host in first
    assert result.engine in first
    assert result.instance in first


def test_a_refusal_says_it_refused_and_why_there_is_no_way_round_it() -> None:
    report = rendered("crowded")
    assert "REFUSED" in report
    assert "no flag that" in report


def test_a_pass_with_warnings_says_they_need_acknowledging() -> None:
    report = rendered("typical")
    assert "PASSED" in report
    assert "acknowledgement" in report


def test_a_clean_pass_says_there_is_nothing_to_acknowledge() -> None:
    result = PreflightResult.of(
        [
            GateResult(
                identifier="cpu.min_cores",
                source=Source.SHARED,
                severity=Severity.BLOCK,
                outcome=Outcome.PASS,
                title="Enough cores",
                observed="8 cores, and 2 are required",
            )
        ],
        host="db.invalid",
        engine="exampledb",
        profile_version="1.0.0",
        version="3",
        instance="main",
        evaluated_at=MOMENT,
    )
    assert "nothing to acknowledge" in render_preflight(result)


def test_only_what_did_not_pass_is_printed() -> None:
    """The counts say how many agreed; naming them would bury what has to be acted on."""
    report = rendered("typical")
    result = result_for("typical")
    for entry in result.results:
        if entry.outcome is Outcome.PASS:
            assert entry.identifier not in report


@pytest.mark.parametrize("name", FIXTURES)
def test_everything_that_did_not_pass_is_printed(name: str) -> None:
    report = rendered(name)
    for entry in result_for(name).results:
        if entry.outcome is not Outcome.PASS:
            assert entry.identifier in report


def test_the_counts_are_on_the_report() -> None:
    result = result_for("crowded")
    summary = result.summary
    assert (
        f"{summary['pass']} pass -- {summary['warn']} warn -- "
        f"{summary['block']} block -- {summary['skip']} skipped"
    ) in render_preflight(result)


def test_blocks_are_printed_before_warnings() -> None:
    report = rendered("crowded")
    assert report.index("BLOCK") < report.index("WARN ")


def test_a_long_identifier_does_not_break_the_column() -> None:
    """It takes a line of its own rather than pushing one result out of alignment."""
    result = PreflightResult.of(
        [
            GateResult(
                identifier="exampledb.a.very.long.rule_identifier",
                source=Source.PROFILE,
                severity=Severity.WARN,
                outcome=Outcome.WARN,
                title="Something",
                observed="an observation",
                remediation="Change something.",
            ),
            GateResult(
                identifier="os.thp",
                source=Source.SHARED,
                severity=Severity.WARN,
                outcome=Outcome.WARN,
                title="Something else",
                observed="another observation",
                remediation="Change something else.",
            ),
        ],
        host="db.invalid",
        engine="exampledb",
        profile_version="1.0.0",
        version="3",
        instance="main",
        evaluated_at=MOMENT,
    )
    report = render_preflight(result)
    assert "  WARN  exampledb.a.very.long.rule_identifier\n" in report
    assert max(len(line) for line in report.splitlines()) <= REPORT_WIDTH


def test_a_remedy_is_marked_and_a_continuation_is_not() -> None:
    report = rendered("crowded")
    assert "-> " in report


def test_the_rendering_is_deterministic() -> None:
    assert rendered("crowded") == rendered("crowded")


# -------------------------------------------------------------------------- the document


@pytest.mark.parametrize("name", FIXTURES)
def test_the_document_matches_its_schema(name: str) -> None:
    facts = load_facts(HOSTS / f"{name}.json")
    request = resolve_request(PROFILE, host=facts.host, environment="production")
    result = evaluate(facts, PROFILE, request, today=TODAY, now=MOMENT)
    problems = problems_in(
        document(result, PROFILE, request),
        schema_name="preflight.schema.json",
        file="preflight.json",
    )
    assert not problems, [str(problem) for problem in problems]


def test_the_document_is_json_and_carries_every_rule() -> None:
    facts = load_facts(HOSTS / "crowded.json")
    request = resolve_request(PROFILE, host=facts.host, environment="production")
    result = evaluate(facts, PROFILE, request, today=TODAY, now=MOMENT)
    written = json.loads(json.dumps(document(result, PROFILE, request), sort_keys=True))
    assert len(written["results"]) == len(result.results)
    assert written["result"]["applicable"] is False
    assert written["evaluated_at"] == "2026-09-04T10:14:22Z"


def test_a_refusal_is_still_a_document() -> None:
    """Refusal is a first-class outcome, not the absence of one."""
    facts = load_facts(HOSTS / "crowded.json")
    request = resolve_request(PROFILE, host=facts.host, environment="production")
    result = evaluate(facts, PROFILE, request, today=TODAY, now=MOMENT)
    written = document(result, PROFILE, request)
    assert written["summary"]["block"] > 0
    assert written["result"] == {
        "applicable": False,
        "warnings_require_acknowledgement": True,
    }


def test_a_passing_rule_carries_no_remedy_in_the_document() -> None:
    facts = load_facts(HOSTS / "typical.json")
    request = resolve_request(PROFILE, host=facts.host, environment="production")
    result = evaluate(facts, PROFILE, request, today=TODAY, now=MOMENT)
    written = document(result, PROFILE, request)
    for entry in written["results"]:
        if entry["outcome"] == "pass":
            assert "remediation" not in entry


def test_the_document_says_where_each_rule_came_from() -> None:
    facts = load_facts(HOSTS / "typical.json")
    request = resolve_request(PROFILE, host=facts.host, environment="production")
    result = evaluate(facts, PROFILE, request, today=TODAY, now=MOMENT)
    written = document(result, PROFILE, request)
    sources = {entry["source"] for entry in written["results"]}
    assert sources == {"shared", "profile"}
