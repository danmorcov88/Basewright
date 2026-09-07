"""What a verify report says, and how it says it.

The rendering is read by somebody who has just been told an instance is not what its plan
says, in a terminal, in a Semaphore task log, and in a documentation image generated on a
machine that may not agree with this one about the console encoding. So the shape of it is
part of the contract: ASCII, a fixed width, and a verdict that says which of the three
things happened.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from basewright.profiles import load_profile
from basewright.profiles.model import Profile
from basewright.report.problems import REPORT_WIDTH
from basewright.report.verify import render_verify
from basewright.verify import Observation, Outcome, read_observation, verify
from basewright.verify.run import CheckResult, VerifyResult

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "test" / "fixtures" / "plan" / "applied.json"
OBSERVED = ROOT / "test" / "fixtures" / "observations" / "observed.json"


@pytest.fixture(scope="module")
def plan() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(PLAN.read_text(encoding="utf-8"))
    return document


@pytest.fixture(scope="module")
def profile() -> Profile:
    return load_profile(ROOT / "profiles" / "postgresql")


def raw() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(OBSERVED.read_text(encoding="utf-8"))
    return document


def observation_from(document: dict[str, Any]) -> Observation:
    return read_observation(document, OBSERVED)


def rendered(plan: dict[str, Any], profile: Profile, document: dict[str, Any]) -> str:
    return render_verify(verify(plan, profile, observation_from(document)))


# --------------------------------------------------------------------------- the shape


def test_the_report_names_the_instance_and_the_plan(plan: dict[str, Any], profile: Profile) -> None:
    report = rendered(plan, profile, raw())

    assert report.startswith("VERIFY  apply-ubuntu2404 -- postgresql 16, instance main")
    assert plan["plan_id"] in report


def test_the_report_says_when_the_instance_was_read(plan: dict[str, Any], profile: Profile) -> None:
    """Not the same moment as the judgement, and a verify report is read months later."""
    assert f"read {raw()['observed_at']}" in rendered(plan, profile, raw())


def test_every_check_appears_passes_included(plan: dict[str, Any], profile: Profile) -> None:
    """Unlike a preflight, which prints only what did not pass. This is the record that an
    instance was proved, and a record listing only failures cannot be told apart from a
    record of a run that asked very little."""
    report = rendered(plan, profile, raw())

    for check in profile.checks:
        assert check.identifier in report


def test_the_report_is_ascii_and_within_the_shared_width(
    plan: dict[str, Any], profile: Profile
) -> None:
    document = raw()
    document["observations"]["parameters"]["settings"]["shared_buffers"] = 1
    report = rendered(plan, profile, document)

    report.encode("ascii")
    for line in report.split("\n"):
        assert len(line) <= REPORT_WIDTH, line


def test_a_passing_check_carries_neither_a_remedy_nor_a_repetition(
    plan: dict[str, Any], profile: Profile
) -> None:
    """On a pass, what was read and what was planned say the same thing twice."""
    report = rendered(plan, profile, raw())

    assert "->" not in report
    assert "planned:" not in report


# ------------------------------------------------------------------------- the verdict


def test_a_matching_instance_reads_verified(plan: dict[str, Any], profile: Profile) -> None:
    report = rendered(plan, profile, raw())

    assert "VERIFIED" in report
    assert "This instance is what the plan says it is." in report


def test_a_mismatch_reads_failed_and_names_what_was_found(
    plan: dict[str, Any], profile: Profile
) -> None:
    document = raw()
    document["observations"]["parameters"]["settings"]["shared_buffers"] = 1
    report = rendered(plan, profile, document)

    assert "FAILED" in report
    planned = next(p for p in plan["parameters"] if p["parameter"] == "shared_buffers")
    assert f"shared_buffers is 1, planned {planned['value']}" in report
    assert "1 check did not match" in report


def test_a_run_that_could_not_ask_reads_unproved(plan: dict[str, Any], profile: Profile) -> None:
    """The third verdict, and the reason the third outcome exists. Nothing contradicts the
    plan and the instance is not verified, and a reader told `FAILED` here would go
    looking in the wrong place."""
    document = raw()
    del document["observations"]["connection"]
    report = rendered(plan, profile, document)

    assert "UNPROVED" in report
    assert "does not verify the instance" in report
    assert "FAILED" not in report


def test_a_failing_run_says_how_much_it_also_could_not_ask(
    plan: dict[str, Any], profile: Profile
) -> None:
    document = raw()
    document["observations"]["service"]["active"] = False
    del document["observations"]["connection"]
    report = rendered(plan, profile, document)

    assert "FAILED" in report
    assert "A further 1 could not be observed at all." in report


@pytest.mark.parametrize(
    "outcome,expected",
    [(Outcome.FAIL, "1 check did not match"), (Outcome.UNOBSERVED, "1 check could not be put")],
)
def test_one_of_something_is_singular(outcome: Outcome, expected: str) -> None:
    """A report that says "1 checks" is a report somebody stops reading carefully."""
    assert expected in render_verify(_one(outcome))


def test_a_long_identifier_takes_a_line_of_its_own(plan: dict[str, Any], profile: Profile) -> None:
    """Rather than pushing that one result out of alignment with every other one."""
    report = rendered(plan, profile, raw())
    lines = report.split("\n")
    named = next(index for index, line in enumerate(lines) if "initialization.matches" in line)

    assert lines[named].rstrip().endswith("postgresql.initialization.matches")
    assert lines[named + 1].strip()


def _one(outcome: Outcome) -> VerifyResult:
    """A result with a single check at one outcome, for the wording cases."""
    return VerifyResult(
        host="db-01.invalid",
        engine="exampledb",
        version="1",
        instance="main",
        plan_id="aaaabbbbcccc",
        observed_at=datetime(2026, 1, 15, 9, 30, 0, tzinfo=UTC),
        results=(
            CheckResult(
                identifier="exampledb.service.running",
                kind="service",
                title="The unit is active",
                outcome=outcome,
                observed="something happened",
                remediation="do something about it",
            ),
        ),
    )


def test_a_result_with_no_checks_at_all_still_renders() -> None:
    """A profile is required to declare at least one, so this is defensive rather than
    reachable -- and a renderer that divides by the number of checks would find out here
    rather than on somebody's console."""
    empty = dataclasses.replace(_one(Outcome.PASS), results=())

    assert "0 pass" in render_verify(empty)
