"""Putting a profile's checks to a reading, and what the whole run comes to.

Three things are worth insisting on here beyond the judgements themselves: that a run
refuses two documents that are not about the same instance rather than reporting on them,
that a kind nobody read is reported as such and leaves the instance unverified, and that a
profile's expression can narrow a kind but never excuse one.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

import pytest

from basewright.profiles import load_profile
from basewright.profiles.model import Profile, VerifyCheck
from basewright.verify import Observation, Outcome, VerifyError, read_observation, verify
from basewright.verify.document import document
from basewright.verify.model import (
    InvalidObservationError,
    MissingObservationError,
    load_observation,
)

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


@pytest.fixture
def observation() -> Observation:
    return load_observation(OBSERVED)


def observation_from(document: dict[str, Any]) -> Observation:
    return read_observation(document, OBSERVED)


def raw() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(OBSERVED.read_text(encoding="utf-8"))
    return document


# ------------------------------------------------------------------- the agreeing case


def test_an_instance_that_matches_its_plan_verifies(
    plan: dict[str, Any], profile: Profile, observation: Observation
) -> None:
    result = verify(plan, profile, observation)

    assert result.verified
    assert result.summary == {"pass": len(profile.checks), "fail": 0, "unobserved": 0}
    assert result.plan_id == plan["plan_id"]


def test_every_check_the_profile_declares_is_reported(
    plan: dict[str, Any], profile: Profile, observation: Observation
) -> None:
    """Passes included. A record that lists only failures cannot be told apart from a
    record of a run that asked very little."""
    result = verify(plan, profile, observation)

    assert [entry.identifier for entry in result.results] == [
        check.identifier for check in profile.checks
    ]


# ---------------------------------------------------- two documents about one instance


def test_a_reading_of_another_plan_is_refused_outright(
    plan: dict[str, Any], profile: Profile
) -> None:
    """Not reported check by check. A plan is named after a digest of its own content, so
    a different id is a different set of promises, and every line of the report that
    followed would compare two unrelated things and present it as a verdict."""
    document = raw()
    document["plan_id"] = "0000deadbeef"

    with pytest.raises(VerifyError, match="0000deadbeef"):
        verify(plan, profile, observation_from(document))


def test_a_reading_from_another_machine_is_refused_outright(
    plan: dict[str, Any], profile: Profile
) -> None:
    document = raw()
    document["host"] = "db-somewhere-else.invalid"

    with pytest.raises(VerifyError, match=re.escape("db-somewhere-else.invalid")):
        verify(plan, profile, observation_from(document))


# ------------------------------------------------------------------ nobody managed to ask


def test_a_kind_nobody_read_is_unobserved_rather_than_passed(
    plan: dict[str, Any], profile: Profile
) -> None:
    document = raw()
    del document["observations"]["connection"]
    result = verify(plan, profile, observation_from(document))

    unobserved = [e for e in result.results if e.outcome is Outcome.UNOBSERVED]
    assert [entry.kind for entry in unobserved] == ["connection"]
    assert "connection" in unobserved[0].observed


def test_a_run_that_could_not_ask_does_not_verify(plan: dict[str, Any], profile: Profile) -> None:
    """The whole of ADR-0025 in one assertion. Nothing contradicts the plan and the
    instance is still not verified, because a question nobody put proves nothing."""
    document = raw()
    del document["observations"]["connection"]
    result = verify(plan, profile, observation_from(document))

    assert result.counting(Outcome.FAIL) == 0
    assert not result.verified


def test_an_instance_that_would_not_answer_leaves_the_root_cause_visible(
    plan: dict[str, Any], profile: Profile
) -> None:
    """A cluster that is down cannot be asked about seven of the eleven. The report has to
    say which one is the reason rather than drowning it in six identical lines."""
    document = raw()
    document["observations"]["service"]["active"] = False
    for kind in ("connection", "version", "parameters", "paths", "log", "auth", "account"):
        del document["observations"][kind]
    result = verify(plan, profile, observation_from(document))

    failed = [e.kind for e in result.results if e.outcome is Outcome.FAIL]
    assert failed == ["service"]
    assert result.counting(Outcome.UNOBSERVED) == 7
    assert not result.verified


def test_a_remediation_travels_with_anything_that_is_not_a_pass(
    plan: dict[str, Any], profile: Profile
) -> None:
    document = raw()
    del document["observations"]["backup"]
    result = verify(plan, profile, observation_from(document))

    for entry in result.results:
        assert bool(entry.remediation) is (entry.outcome is not Outcome.PASS)


# ---------------------------------------------------------- what a profile may add


def test_a_profiles_expression_can_refuse_what_the_kind_allows(
    plan: dict[str, Any], profile: Profile
) -> None:
    """The port kind judges the port, because the port is what the plan carries. That the
    instance is on no address but loopback is this profile's decision, written where
    somebody arguing with it would look."""
    document = raw()
    document["observations"]["port"]["bound"] = [{"address": "0.0.0.0", "port": 5432}]
    result = verify(plan, profile, observation_from(document))

    port = next(entry for entry in result.results if entry.kind == "port")
    assert port.outcome is Outcome.FAIL
    assert port.expression == "observed.port.loopback_only"


def test_an_expression_is_a_narrowing_and_never_an_excuse(
    plan: dict[str, Any], profile: Profile, observation: Observation
) -> None:
    """It runs only on a kind that already passed, so a profile cannot write one that
    turns a mismatch into a pass. Checked by giving one that is always true and a reading
    the kind refuses."""
    narrowed = _with_expression(profile, "port", "1 == 1")
    document = raw()
    document["observations"]["port"]["bound"] = [{"address": "127.0.0.1", "port": 9999}]
    result = verify(plan, narrowed, observation_from(document))

    port = next(entry for entry in result.results if entry.kind == "port")
    assert port.outcome is Outcome.FAIL


def test_an_expression_reading_something_nobody_observed_is_unobserved(
    plan: dict[str, Any], profile: Profile
) -> None:
    """Reading an unobserved kind is not a misspelling, and it is not a failure of the
    instance either."""
    narrowed = _with_expression(profile, "service", "observed.connection.accepted")
    document = raw()
    del document["observations"]["connection"]
    result = verify(plan, narrowed, observation_from(document))

    service = next(entry for entry in result.results if entry.kind == "service")
    assert service.outcome is Outcome.UNOBSERVED


def test_an_expression_that_cannot_be_read_is_a_defect_in_the_profile(
    plan: dict[str, Any], profile: Profile, observation: Observation
) -> None:
    """Loud and named, because the person who has to fix it is editing that file -- not an
    instance that fell short, and not something to report as a failing check."""
    broken = _with_expression(profile, "service", "observed.srevice.active")

    with pytest.raises(VerifyError, match=re.escape("postgresql.service.running")):
        verify(plan, broken, observation)


def test_an_expression_that_is_not_a_question_is_refused(
    plan: dict[str, Any], profile: Profile, observation: Observation
) -> None:
    written_as_a_sum = _with_expression(profile, "service", "1 + 1")

    with pytest.raises(VerifyError):
        verify(plan, written_as_a_sum, observation)


def _with_expression(profile: Profile, kind: str, expression: str) -> Profile:
    """The same profile with one check narrowed. Built from the real one so a case cannot
    quietly stop being about a check this repository actually ships."""
    checks = tuple(
        VerifyCheck(
            identifier=check.identifier,
            kind=check.kind,
            title=check.title,
            remediation=check.remediation,
            expr=expression if check.kind == kind else check.expr,
        )
        for check in profile.checks
    )
    return dataclasses.replace(profile, checks=checks)


# ------------------------------------------------------------------ reading a document


def test_a_document_that_is_not_there_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(MissingObservationError):
        load_observation(tmp_path / "nowhere.json")


def test_a_document_that_is_not_json_is_refused_with_a_report(tmp_path: Path) -> None:
    path = tmp_path / "observation.json"
    path.write_text("the cluster is fine, honestly", encoding="utf-8")

    with pytest.raises(InvalidObservationError) as refused:
        load_observation(path)
    assert "readable JSON" in refused.value.report()


def test_a_document_carrying_a_key_the_schema_does_not_define_is_refused() -> None:
    document = raw()
    document["observations"]["service"]["healthy"] = True

    with pytest.raises(InvalidObservationError) as refused:
        observation_from(document)
    assert "healthy" in refused.value.report()


def test_a_document_of_a_version_this_build_does_not_implement_is_refused() -> None:
    document = raw()
    document["schema_version"] = "2"

    with pytest.raises(InvalidObservationError):
        observation_from(document)


# --------------------------------------------------------------------- the artifact


def test_the_document_says_what_the_run_decided(
    plan: dict[str, Any], profile: Profile, observation: Observation
) -> None:
    written = document(verify(plan, profile, observation))

    assert written["schema_version"] == "1"
    assert written["result"] == {"verified": True}
    assert written["plan_id"] == plan["plan_id"]
    assert written["observed_at"] == raw()["observed_at"]
    assert len(written["results"]) == len(profile.checks)


def test_the_document_leaves_out_what_a_check_did_not_carry(
    plan: dict[str, Any], profile: Profile, observation: Observation
) -> None:
    """A reader should be able to tell a check with no remediation from one whose
    remediation was blank, and the schema draws that line by absence."""
    written = document(verify(plan, profile, observation))
    passing = next(entry for entry in written["results"] if entry["outcome"] == "pass")

    assert "remediation" not in passing
