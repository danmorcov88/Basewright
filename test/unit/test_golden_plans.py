"""The committed goldens, and the determinism that makes them worth committing.

A golden plan is the review mechanism for a tuning decision: a change to a sizing rule
shows up in a pull request as a diff of the values it produced on five real machines,
which is something a reviewer can judge without reading the evaluator. That only works
while two runs of the same inputs agree byte for byte, so that is checked here as well,
and separately, because a golden that failed for both reasons at once would say neither.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from basewright.planner.schema import plan_problems
from basewright.schema import problems_in

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from render_goldens import (  # noqa: E402
    APPLIED,
    CHANGED,
    EDITED,
    FIXTURES,
    GOLDEN,
    OBSERVED,
    PROFILES,
    TAMPERED_FROM,
    WIDENED,
    build,
)


@pytest.fixture(scope="module")
def goldens() -> dict[Path, str]:
    return build()


#: The engines whose answers are committed. Two of them now, which is the point of the
#: arrangement rather than an accident of it: the same fixture hosts go through a fictional
#: engine and a real one, and every check below is made once per engine.
ENGINES: tuple[str, ...] = tuple(engine for engine, _ in PROFILES)


def under(goldens: dict[Path, str], engine: str, directory: str) -> set[str]:
    """The names written into one of the golden directories, for one engine.

    The renderer also writes one file outside them -- a plan that is wrong on purpose --
    so a check that means "the goldens" has to say which ones it means.
    """
    return {path.stem for path in goldens if path.parent == GOLDEN / engine / directory}


def test_the_committed_goldens_are_what_the_pipeline_produces(goldens: dict[Path, str]) -> None:
    """Regenerate with tools/render_goldens.py, then read the diff. That is the review."""
    stale = [
        path.relative_to(ROOT).as_posix()
        for path, content in goldens.items()
        if not path.is_file() or path.read_text(encoding="utf-8") != content
    ]

    assert stale == []


def test_nothing_is_committed_that_no_fixture_produces() -> None:
    """A golden nobody generates any more is a file that agrees with everything for ever."""
    produced = {path for path in build() if GOLDEN in path.parents}
    committed = {
        path
        for engine in ENGINES
        for directory in ("plan", "rendered", "refused", "verified")
        for path in (GOLDEN / engine / directory).glob("*")
    }

    assert committed == produced


def test_every_engine_that_ships_has_its_answers_committed() -> None:
    """A profile added to profiles/ and not to the goldens is a set of tuning decisions
    nobody reviews the diff of, which is the whole mechanism."""
    committed = {path.name for path in GOLDEN.iterdir() if path.is_dir()}

    assert committed == set(ENGINES)


def test_two_runs_of_the_same_inputs_are_identical(goldens: dict[Path, str]) -> None:
    """Determinism is the property the whole review mechanism rests on."""
    assert build() == goldens


@pytest.mark.parametrize("engine", ENGINES)
def test_every_fixture_host_is_accounted_for(goldens: dict[Path, str], engine: str) -> None:
    """A host that quietly stopped being planned would leave the suite passing."""
    names = under(goldens, engine, "plan") | under(goldens, engine, "refused")

    assert names == set(FIXTURES)


@pytest.mark.parametrize("engine", ENGINES)
def test_every_plan_that_was_produced_was_also_rendered(
    goldens: dict[Path, str], engine: str
) -> None:
    """The rendering is what a person reads, so it is reviewed by diff like the plan is."""
    planned = under(goldens, engine, "plan")

    assert planned == under(goldens, engine, "rendered")
    assert planned


@pytest.mark.parametrize("engine", ENGINES)
def test_each_engine_refuses_a_host_and_plans_another(
    goldens: dict[Path, str], engine: str
) -> None:
    """A profile that plans every fixture is one whose gates are not doing anything, and a
    profile that refuses every fixture is one nobody could demonstrate."""
    assert under(goldens, engine, "plan")
    assert under(goldens, engine, "refused")


def test_every_golden_plan_validates_against_the_contract(goldens: dict[Path, str]) -> None:
    """The plans, and the plan that is wrong on purpose -- which is wrong about its name
    rather than about its shape. The renderer writes other documents too, a verify report
    and a reading of an instance, and those answer to contracts of their own."""
    plans = [
        (path, content)
        for path, content in goldens.items()
        if path.suffix == ".json" and path.parent.name == "plan"
    ]
    plans.append((EDITED, goldens[EDITED]))

    assert plans
    for path, content in plans:
        problems = plan_problems(json.loads(content))
        assert problems == [], f"{path.name}: " + "\n".join(str(p) for p in problems)


def test_every_verify_report_validates_against_its_own_contract(
    goldens: dict[Path, str],
) -> None:
    """The other end of the loop answers to schema/verification.schema.json, which is a
    different closed contract and is checked as one."""
    reports = [
        (path, content)
        for path, content in goldens.items()
        if path.suffix == ".json" and path.parent.name == "verified"
    ]

    assert reports
    for path, content in reports:
        problems = problems_in(
            json.loads(content), schema_name="verification.schema.json", file=path.name
        )
        assert problems == [], f"{path.name}: " + "\n".join(str(p) for p in problems)


def test_the_committed_reading_validates_against_the_observation_contract() -> None:
    """It came off a container rather than being written, so what it proves is that a
    document a role really produced is one the core really accepts."""
    problems = problems_in(
        json.loads(OBSERVED.read_text(encoding="utf-8")),
        schema_name="observation.schema.json",
        file=OBSERVED.name,
    )

    assert problems == []


def test_a_refused_host_gets_a_report_rather_than_a_plan(goldens: dict[Path, str]) -> None:
    """Refusal is a first-class outcome, so it has an artifact of its own."""
    refusals = {path.stem for path in goldens if path.parent.name == "refused"}

    assert refusals
    for path, content in goldens.items():
        if path.parent.name == "refused":
            assert "BLOCK" in content


def test_the_tampered_fixture_is_a_plan_that_lies_about_its_name(
    goldens: dict[Path, str],
) -> None:
    """It is generated rather than committed by hand, so it cannot fall behind the plan
    it is a copy of, and the check that notices an edited plan has something real to
    notice."""
    edited = next(path for path in goldens if path.name == "edited.json")
    document = json.loads(goldens[edited])
    original = json.loads(goldens[TAMPERED_FROM])

    assert GOLDEN not in edited.parents, "a plan that is wrong on purpose is not a golden"
    assert document["plan_id"] == original["plan_id"]
    assert document["parameters"][0]["value"] != original["parameters"][0]["value"]


def test_every_golden_is_ascii(goldens: dict[Path, str]) -> None:
    """These are read in terminals and diffed on machines that disagree about encodings."""
    for path, content in goldens.items():
        assert content.isascii(), path.name


# ------------------------------------------------------- the other end of the loop


def test_a_verify_report_is_committed_for_both_endings(goldens: dict[Path, str]) -> None:
    """Both, because a report that only ever passes has not been shown to be looking, and
    the diff on the failing one is where a change to how a refusal reads shows up."""
    engine = json.loads(APPLIED.read_text(encoding="utf-8"))["request"]["engine"]

    assert under(goldens, engine, "verified") == {"observed", "changed"}


def test_the_committed_reading_verifies_and_the_changed_one_does_not(
    goldens: dict[Path, str],
) -> None:
    engine = json.loads(APPLIED.read_text(encoding="utf-8"))["request"]["engine"]
    verified = GOLDEN / engine / "verified"

    assert json.loads(goldens[verified / "observed.json"])["result"]["verified"] is True
    assert json.loads(goldens[verified / "changed.json"])["result"]["verified"] is False


def test_the_changed_reading_differs_from_the_real_one_in_exactly_one_value(
    goldens: dict[Path, str],
) -> None:
    """Generated rather than committed by hand, so it cannot fall behind the reading it is
    a copy of -- the same treatment the tampered plan gets, and for the same reason."""
    real = json.loads(OBSERVED.read_text(encoding="utf-8"))
    changed = json.loads(goldens[CHANGED])
    name, value = WIDENED

    real["observations"]["parameters"]["settings"][name] = value
    assert changed == real
    assert GOLDEN not in CHANGED.parents, "a reading that is wrong on purpose is not a golden"


def test_the_changed_report_names_the_parameter_that_was_widened(
    goldens: dict[Path, str],
) -> None:
    """The picture in the README and the case the molecule scenario proves on a container
    are the same case, down to the parameter."""
    engine = json.loads(APPLIED.read_text(encoding="utf-8"))["request"]["engine"]
    report = goldens[GOLDEN / engine / "verified" / "changed.txt"]
    name, _ = WIDENED

    assert name in report
    assert "FAILED" in report
