"""Every kind, both ways round, and the third way when there is one.

The test policy asks a gate for both of its outcomes. A verify check has three, and the
third is the one worth insisting on: a run that could not put a question to an instance
must not report the same thing as a run that put it and got the right answer.

Table-driven against a plan and a reading that agree, with one thing changed per case, for
the same reason the sizing tests are: what a judgement gets wrong is one comparison out of
eleven, and a case that built its own plan would be testing the fixture as much as the
judgement.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from basewright.verify.judge import JUDGEMENTS, loopback_only
from basewright.verify.model import Outcome

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "test" / "fixtures" / "plan" / "applied.json"
OBSERVED = ROOT / "test" / "fixtures" / "observations" / "observed.json"


@pytest.fixture(scope="module")
def plan() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(PLAN.read_text(encoding="utf-8"))
    return document


@pytest.fixture(scope="module")
def readings() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(OBSERVED.read_text(encoding="utf-8"))
    observations: dict[str, Any] = document["observations"]
    return observations


def judged(kind: str, plan: dict[str, Any], reading: dict[str, Any]) -> Outcome:
    """One kind's judgement, as an outcome."""
    outcome, _, _ = JUDGEMENTS[kind](plan, reading)
    return outcome


# ------------------------------------------------------------------- the agreeing case


def test_the_fixture_agrees_with_the_plan_on_every_kind(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    """The baseline every case below changes one thing in.

    Worth its own test rather than left implicit: if the fixture stopped agreeing, every
    failing case below would go on passing for the wrong reason.
    """
    for kind, reading in readings.items():
        assert judged(kind, plan, reading) is Outcome.PASS, kind


def test_every_kind_the_schema_allows_has_a_judgement() -> None:
    """A kind a profile could name and nothing could judge would never run."""
    schema = json.loads((ROOT / "schema" / "verify.schema.json").read_text(encoding="utf-8"))
    declared = set(schema["$defs"]["check"]["properties"]["kind"]["enum"])
    assert declared == set(JUDGEMENTS)


def test_every_kind_is_exercised_by_the_fixture(readings: dict[str, Any]) -> None:
    """And the fixture carries a reading for each, so nothing above is vacuous."""
    assert set(readings) == set(JUDGEMENTS)


# ------------------------------------------------------------------ one thing at a time

#: One case per way a kind can be wrong: the kind, what to change in its reading, and what
#: that should come to. Written as a mutation of an agreeing reading rather than as a
#: reading of its own, so that a case cannot quietly stop being about the thing it names.
CASES: tuple[tuple[str, str, dict[str, Any], Outcome], ...] = (
    ("service", "a unit that is not running", {"active": False}, Outcome.FAIL),
    ("service", "a unit that will not come back", {"enabled": False}, Outcome.FAIL),
    ("service", "some other unit entirely", {"unit": "mariadb"}, Outcome.FAIL),
    ("port", "nothing listening at all", {"bound": []}, Outcome.FAIL),
    (
        "port",
        "a port nobody planned",
        {"bound": [{"address": "127.0.0.1", "port": 5433}]},
        Outcome.FAIL,
    ),
    (
        "port",
        "the planned port and one more",
        {
            "bound": [
                {"address": "127.0.0.1", "port": 5432},
                {"address": "127.0.0.1", "port": 6432},
            ]
        },
        Outcome.FAIL,
    ),
    ("connection", "a refusal", {"accepted": False, "detail": "no pg_hba entry"}, Outcome.FAIL),
    ("version", "the wrong major", {"reported": "15.7", "major": "15"}, Outcome.FAIL),
    ("log", "no log at all", {"exists": False}, Outcome.FAIL),
    ("log", "a log from a previous life", {"written_since_start": False}, Outcome.FAIL),
    ("backup", "a path nobody can write to", {"writable": False}, Outcome.FAIL),
    ("auth", "an instance that reported no rules", {"rules": []}, Outcome.UNOBSERVED),
    ("account", "an instance that reported no accounts", {"roles": []}, Outcome.UNOBSERVED),
)


@pytest.mark.parametrize("kind,description,change,expected", CASES, ids=[case[1] for case in CASES])
def test_one_thing_changed(
    kind: str,
    description: str,
    change: dict[str, Any],
    expected: Outcome,
    plan: dict[str, Any],
    readings: dict[str, Any],
) -> None:
    del description
    reading = {**copy.deepcopy(readings[kind]), **change}
    assert judged(kind, plan, reading) is expected


# ------------------------------------------------- the kinds whose readings are nested


def test_a_parameter_that_reads_back_wrong_fails(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    reading = copy.deepcopy(readings["parameters"])
    reading["settings"]["shared_buffers"] = 1
    outcome, observed, _ = JUDGEMENTS["parameters"](plan, reading)

    assert outcome is Outcome.FAIL
    assert "shared_buffers" in observed


def test_a_parameter_the_server_has_never_heard_of_fails(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    """Worse than a wrong value: nothing will ever read it, so nothing will ever report it."""
    reading = copy.deepcopy(readings["parameters"])
    reading["unknown"] = ["shared_bufferz"]
    outcome, observed, _ = JUDGEMENTS["parameters"](plan, reading)

    assert outcome is Outcome.FAIL
    assert "shared_bufferz" in observed


def test_a_parameter_nobody_asked_about_is_unobserved(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    """Not a failure. The plan names it, the server was never asked, and the difference
    between those two is the whole reason the third outcome exists."""
    reading = copy.deepcopy(readings["parameters"])
    del reading["settings"]["work_mem"]
    outcome, observed, _ = JUDGEMENTS["parameters"](plan, reading)

    assert outcome is Outcome.UNOBSERVED
    assert "work_mem" in observed


def test_a_value_read_back_as_a_string_does_not_pass_for_a_number(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    """A server answering "8589934592" was asked in the wrong units, and coercing here
    would hide that in the one place nobody would look."""
    reading = copy.deepcopy(readings["parameters"])
    reading["settings"]["shared_buffers"] = str(reading["settings"]["shared_buffers"])

    assert judged("parameters", plan, reading) is Outcome.FAIL


def test_data_stored_somewhere_the_plan_does_not_describe_fails(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    reading = copy.deepcopy(readings["paths"])
    reading["resolved"]["data"] = "/srv/somewhere-else"
    outcome, observed, _ = JUDGEMENTS["paths"](plan, reading)

    assert outcome is Outcome.FAIL
    assert "/srv/somewhere-else" in observed


def test_a_purpose_the_instance_has_no_notion_of_is_not_a_failure(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    """A backup destination is a place the plan puts things rather than a place the
    instance knows about, and the check that proves it is the backup kind."""
    outcome, observed, _ = JUDGEMENTS["paths"](plan, readings["paths"])

    assert outcome is Outcome.PASS
    assert "backup" in observed


def test_an_instance_reporting_no_paths_at_all_is_unobserved(plan: dict[str, Any]) -> None:
    assert judged("paths", plan, {"resolved": {}}) is Outcome.UNOBSERVED


def test_a_password_free_rule_off_the_machine_fails(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    reading = copy.deepcopy(readings["auth"])
    reading["rules"].append(
        {"method": "trust", "local": False, "address": "0.0.0.0/0", "password_required": False}
    )
    outcome, observed, _ = JUDGEMENTS["auth"](plan, reading)

    assert outcome is Outcome.FAIL
    assert "trust" in observed and "0.0.0.0/0" in observed


def test_a_password_free_rule_on_the_machine_is_fine(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    """The fixture already has one -- the service account over the local socket, identified
    by the operating system. Refusing that would refuse every correctly built instance."""
    rules = readings["auth"]["rules"]

    assert any(not rule["password_required"] and rule["local"] for rule in rules)
    assert judged("auth", plan, readings["auth"]) is Outcome.PASS


def test_an_account_that_can_log_in_without_a_password_fails(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    reading = copy.deepcopy(readings["account"])
    reading["roles"].append(
        {"name": "reporting", "can_login": True, "password_set": False, "superuser": False}
    )
    outcome, observed, _ = JUDGEMENTS["account"](plan, reading)

    assert outcome is Outcome.FAIL
    assert "reporting" in observed


def test_an_account_that_cannot_log_in_needs_no_password(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    reading = copy.deepcopy(readings["account"])
    reading["roles"].append(
        {"name": "readers", "can_login": False, "password_set": False, "superuser": False}
    )

    assert judged("account", plan, reading) is Outcome.PASS


@pytest.mark.parametrize(
    "setting,value",
    [("encoding", "LATIN1"), ("data_checksums", False), ("start_conf", "manual")],
)
def test_an_instance_created_differently_fails(
    setting: str, value: Any, plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    """The three that cannot be put right in place, which is why they are checked at all."""
    reading = copy.deepcopy(readings["initialization"])
    reading["settings"][setting] = value
    outcome, observed, _ = JUDGEMENTS["initialization"](plan, reading)

    assert outcome is Outcome.FAIL
    assert setting in observed


def test_an_initialization_setting_nobody_asked_about_is_unobserved(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    """The plan promises three, the reading carries two, and nobody proved the third.
    Not a failure: the instance may well have been created with it."""
    reading = copy.deepcopy(readings["initialization"])
    del reading["settings"]["start_conf"]
    outcome, observed, _ = JUDGEMENTS["initialization"](plan, reading)

    assert outcome is Outcome.UNOBSERVED
    assert "start_conf" in observed


def test_an_instance_created_in_another_locale_fails(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    reading = copy.deepcopy(readings["initialization"])
    reading["locale"] = "C.UTF-8"
    outcome, observed, _ = JUDGEMENTS["initialization"](plan, reading)

    assert outcome is Outcome.FAIL
    assert "C.UTF-8" in observed


# ------------------------------------------------------- what the plan does not promise


@pytest.mark.parametrize(
    "kind,section",
    [
        ("service", "packages"),
        ("parameters", "parameters"),
        ("paths", "layout"),
        ("initialization", "initialization"),
    ],
)
def test_a_promise_the_plan_does_not_make_is_unobserved(
    kind: str, section: str, plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    """A profile asking to verify something the plan does not carry is a defect in the
    profile, and the loudest place to find it is the report rather than a traceback."""
    without = {key: value for key, value in plan.items() if key != section}

    assert judged(kind, without, readings[kind]) is Outcome.UNOBSERVED


def test_a_plan_with_no_port_leaves_the_port_unobserved(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    without = copy.deepcopy(plan)
    del without["request"]["port"]

    assert judged("port", without, readings["port"]) is Outcome.UNOBSERVED


def test_a_plan_with_no_version_leaves_the_version_unobserved(
    plan: dict[str, Any], readings: dict[str, Any]
) -> None:
    without = copy.deepcopy(plan)
    del without["request"]["version"]

    assert judged("version", without, readings["version"]) is Outcome.UNOBSERVED


# --------------------------------------------------------------- the derived answer


@pytest.mark.parametrize(
    "bound,expected",
    [
        ([{"address": "127.0.0.1", "port": 5432}], True),
        ([{"address": "::1", "port": 5432}], True),
        ([{"address": "127.0.0.1", "port": 5432}, {"address": "::1", "port": 5432}], True),
        ([{"address": "0.0.0.0", "port": 5432}], False),
        ([{"address": "127.0.0.1", "port": 5432}, {"address": "10.0.0.4", "port": 5432}], False),
        ([], False),
    ],
)
def test_what_counts_as_reachable_only_from_this_machine(
    bound: list[dict[str, Any]], expected: bool
) -> None:
    """Nothing bound at all is not loopback-only. It is an instance nobody can reach, and
    saying "yes, only from here" about it would be true and useless."""
    assert loopback_only(bound) is expected
