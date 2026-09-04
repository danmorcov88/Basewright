"""Every profile in the repository, and the plan contract, validated against the schema.

This is the check the build runs. It has two halves, and the second one is currently
vacuous on purpose: there is no engine profile yet, and a fixture parked in ``profiles/``
to make the number look better would make the status page a lie. The fixtures below are
what actually exercises the schema until a real profile lands, at which point this file
starts checking it without being touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from basewright.planner.schema import plan_problems
from basewright.profiles import Profile, load_profile, profile_directories

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "profiles"
FIXTURES = ROOT / "test" / "fixtures" / "profiles"
#: The plan the contract is exercised against is a real one, produced by the pipeline and
#: committed as a golden. A hand-written example would drift from what plan actually emits,
#: and the drift would be invisible in exactly the direction that matters.
PLAN_FIXTURE = ROOT / "test" / "golden" / "plan" / "typical.json"

#: Fixture profiles that are meant to be valid. The others are broken deliberately and
#: are exercised by the loader's own tests.
VALID_FIXTURES = ("exampledb",)


def plan_document() -> dict[str, object]:
    document: dict[str, object] = json.loads(PLAN_FIXTURE.read_text(encoding="utf-8"))
    return document


@pytest.mark.parametrize("name", VALID_FIXTURES)
def test_fixture_profile_is_valid(name: str) -> None:
    """A fictional engine is enough to prove the schema needs no real one."""
    profile = load_profile(FIXTURES / name)
    assert isinstance(profile, Profile)


def test_every_profile_in_the_repository_is_valid() -> None:
    """Whatever is in profiles/ has to load. Today that is nothing, which is honest."""
    for directory in profile_directories(PROFILES):
        load_profile(directory)


def test_the_plan_contract_accepts_a_complete_plan() -> None:
    assert plan_problems(plan_document()) == []


def test_the_plan_contract_refuses_an_unknown_key() -> None:
    """A field apply does not read is a field that promises something nothing delivers."""
    document = plan_document()
    document["accept_warnings"] = True

    problems = plan_problems(document)

    assert [problem.location for problem in problems] == ["accept_warnings"]


def test_the_plan_contract_has_nowhere_to_put_a_secret() -> None:
    """The strongest form of "never log a secret" is a document with no field for one."""
    document = plan_document()
    secrets = document["secrets"]
    assert isinstance(secrets, list)
    secrets[0]["value"] = "hunter2"

    problems = plan_problems(document)

    assert [problem.location for problem in problems] == ["secrets[0].value"]


def test_the_plan_contract_refuses_a_plan_carrying_a_block() -> None:
    """A block produces a refusal, not a plan, so a plan cannot report one."""
    document = plan_document()
    preflight = document["preflight"]
    assert isinstance(preflight, dict)
    preflight["summary"]["block"] = 1

    problems = plan_problems(document)

    assert [problem.location for problem in problems] == ["preflight.summary.block"]
