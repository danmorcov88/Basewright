"""The plan: what it carries, what it refuses to carry, and what it is called.

Three things are worth more than the rest here. That a block produces no plan at all,
because a partial plan is the thing this project exists to stop being possible. That the
plan is named after its own content and not after the moment it was written, because a
name that changes every second is not a name. And that apply, which reads the plan and
nothing else, finds every value it needs in it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from basewright import __version__
from basewright.facts import HostFacts, load_facts
from basewright.planner import PlanError, build_plan, plan_id_for, rendered
from basewright.planner.schema import plan_problems
from basewright.preflight import evaluate
from basewright.profiles import Profile, load_profile
from basewright.request import Request, resolve_request

ROOT = Path(__file__).resolve().parents[2]
HOSTS = ROOT / "test" / "fixtures" / "hosts"
PROFILE = ROOT / "test" / "fixtures" / "profiles" / "exampledb"

MOMENT = datetime(2026, 1, 15, 9, 30, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def profile() -> Profile:
    return load_profile(PROFILE)


def host(name: str) -> HostFacts:
    return load_facts(HOSTS / f"{name}.json")


def request_for(profile: Profile, facts: HostFacts) -> Request:
    return resolve_request(profile, host=facts.host, environment="production")


def plan_for(profile: Profile, name: str, **overrides: Any) -> dict[str, Any]:
    facts = host(name)
    request = request_for(profile, facts)
    gates = evaluate(facts, profile, request, today=MOMENT.date(), now=MOMENT)
    return build_plan(facts, profile, request, gates, now=overrides.get("now", MOMENT))


@pytest.fixture(scope="module")
def plan(profile: Profile) -> dict[str, Any]:
    return plan_for(profile, "typical")


# ------------------------------------------------------------------- a block ends it


def test_a_blocked_host_produces_no_plan(profile: Profile) -> None:
    """There is no partial plan and no flag that makes one. That is the whole design."""
    facts = host("crowded")
    request = request_for(profile, facts)
    gates = evaluate(facts, profile, request, today=MOMENT.date(), now=MOMENT)

    assert gates.blocked
    with pytest.raises(PlanError, match="blocked by preflight"):
        build_plan(facts, profile, request, gates, now=MOMENT)


def test_a_plan_can_never_carry_a_block(plan: dict[str, Any]) -> None:
    assert plan["preflight"]["summary"]["block"] == 0


# ---------------------------------------------------------------------- what it says


def test_the_plan_validates_against_its_own_contract(plan: dict[str, Any]) -> None:
    problems = plan_problems(plan)

    assert problems == [], "\n".join(str(problem) for problem in problems)


def test_every_parameter_carries_the_rule_and_the_reason(plan: dict[str, Any]) -> None:
    """A number without a reason is exactly the situation Basewright exists to end."""
    assert plan["parameters"]
    for parameter in plan["parameters"]:
        assert parameter["rule"]
        assert len(parameter["why"]) > 10


def test_parameters_are_listed_in_the_order_the_profile_wrote_them(
    plan: dict[str, Any], profile: Profile
) -> None:
    written = [rule.parameter for rule in profile.sizing]

    assert [entry["parameter"] for entry in plan["parameters"]] == written


def test_a_parameter_computed_from_another_one_is_still_correct(plan: dict[str, Any]) -> None:
    """work_memory is written above the rule it depends on, deliberately."""
    values = {entry["parameter"]: entry["value"] for entry in plan["parameters"]}

    assert values["work_memory"] == int(0.25 * 34359738368 / (values["max_connections"] * 2))


def test_every_planned_path_says_who_owns_it_and_what_carries_it(plan: dict[str, Any]) -> None:
    for entry in plan["layout"]["paths"]:
        assert entry["owner"] and entry["group"]
        assert entry["mount"].startswith("/")


def test_the_plan_carries_what_apply_needs_to_install(plan: dict[str, Any]) -> None:
    """Apply consumes the plan and nothing else, so the plan carries the package names."""
    packages = plan["packages"]

    assert packages["install"] == ["exampledb-server-3", "exampledb-client-3"]
    assert packages["service"] == "exampledb@3-main"
    assert packages["repository"]["suite"] == "noble", "the host's code name, filled in"


def test_the_plan_carries_where_every_configuration_file_lands(plan: dict[str, Any]) -> None:
    destinations = [entry["destination"] for entry in plan["configuration"]]

    assert destinations == [
        "/etc/basewright/exampledb/main/exampledb.conf",
        "/etc/basewright/exampledb/main/access.conf",
    ]
    assert sum(entry["carries_parameters"] for entry in plan["configuration"]) == 1


def test_a_host_setting_is_shown_as_a_change_from_what_it_is_now(plan: dict[str, Any]) -> None:
    swappiness = next(entry for entry in plan["tunables"] if entry["name"] == "vm.swappiness")

    assert (swappiness["observed"], swappiness["value"]) == (60, 10)
    change = next(entry for entry in plan["changes"] if "vm.swappiness" in entry["description"])
    assert (change["action"], change["from"], change["to"]) == ("modify", "60", "10")


def test_a_setting_already_at_the_wanted_value_is_not_listed_as_a_change(
    profile: Profile,
) -> None:
    """Apply still holds the host to it. It is simply not a change apply would make."""
    large = plan_for(profile, "large")

    assert all(entry["observed"] == entry["value"] for entry in large["tunables"])
    assert not [entry for entry in large["changes"] if entry["action"] == "modify"]


def test_nothing_is_ever_removed(plan: dict[str, Any]) -> None:
    """Apply creates and configures. The vocabulary has no third word on purpose."""
    assert {entry["action"] for entry in plan["changes"]} <= {"add", "modify"}


def test_a_secret_is_named_and_located_and_never_carried(plan: dict[str, Any]) -> None:
    secret = plan["secrets"][0]

    assert secret["location"] == "basewright/db-typical.invalid/exampledb/main/admin"
    assert set(secret) == {"name", "location", "description"}


# ---------------------------------------------------------------------- what it warns


def test_warnings_from_the_gates_and_from_sizing_are_counted_together(
    profile: Profile,
) -> None:
    """One acknowledgement, so one count. A warning raised after the gates closed is not
    a lesser warning."""
    large = plan_for(profile, "large")
    gates = large["preflight"]["summary"]["warn"]
    advisories = sum(1 for entry in large["parameters"] if "above_advisory" in entry)

    assert advisories == 1
    assert large["result"]["warnings"] == gates + advisories
    assert large["result"]["warnings_require_acknowledgement"]


# ------------------------------------------------------------------ what it is called


def test_the_same_inputs_produce_the_same_plan(profile: Profile) -> None:
    assert rendered(plan_for(profile, "typical")) == rendered(plan_for(profile, "typical"))


def test_two_plans_that_differ_only_in_when_share_an_id(profile: Profile) -> None:
    """The moment a plan was written is not part of what it decided."""
    later = datetime(2027, 3, 1, 18, 45, 0, tzinfo=UTC)

    first = plan_for(profile, "typical")
    second = plan_for(profile, "typical", now=later)

    assert first["generated_at"] != second["generated_at"]
    assert first["plan_id"] == second["plan_id"]


def test_a_different_host_produces_a_different_id(profile: Profile) -> None:
    assert plan_for(profile, "typical")["plan_id"] != plan_for(profile, "large")["plan_id"]


def test_the_id_is_computed_over_a_document_that_never_had_the_moment_in_it() -> None:
    """Stated as a refusal rather than as a comment, so it cannot quietly stop being true."""
    with pytest.raises(PlanError, match="without generated_at"):
        plan_id_for({"generated_at": "2026-01-15T09:30:00Z"})


def test_changing_anything_else_changes_the_id() -> None:
    first = plan_id_for({"schema_version": "1", "parameters": [{"value": 1}]})
    second = plan_id_for({"schema_version": "1", "parameters": [{"value": 2}]})

    assert first != second


def test_the_plan_records_which_tool_made_it(plan: dict[str, Any]) -> None:
    assert plan["tool_version"] == __version__


# -------------------------------------------------------------------------- rendering


def test_the_artifact_ends_with_one_newline(plan: dict[str, Any]) -> None:
    written = rendered(plan)

    assert written.endswith("}\n")
    assert not written.endswith("}\n\n")
