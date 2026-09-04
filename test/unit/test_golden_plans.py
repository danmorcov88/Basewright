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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from render_goldens import FIXTURES, GOLDEN, build  # noqa: E402


@pytest.fixture(scope="module")
def goldens() -> dict[Path, str]:
    return build()


def under(goldens: dict[Path, str], directory: str) -> set[str]:
    """The names written into one of the golden directories.

    The renderer also writes one file outside them -- a plan that is wrong on purpose --
    so a check that means "the goldens" has to say which ones it means.
    """
    return {path.stem for path in goldens if path.parent == GOLDEN / directory}


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
        for directory in ("plan", "rendered", "refused")
        for path in (GOLDEN / directory).glob("*")
    }

    assert committed == produced


def test_two_runs_of_the_same_inputs_are_identical(goldens: dict[Path, str]) -> None:
    """Determinism is the property the whole review mechanism rests on."""
    assert build() == goldens


def test_every_fixture_host_is_accounted_for(goldens: dict[Path, str]) -> None:
    """A host that quietly stopped being planned would leave the suite passing."""
    names = under(goldens, "plan") | under(goldens, "refused")

    assert names == set(FIXTURES)


def test_every_plan_that_was_produced_was_also_rendered(goldens: dict[Path, str]) -> None:
    """The rendering is what a person reads, so it is reviewed by diff like the plan is."""
    planned = under(goldens, "plan")

    assert planned == under(goldens, "rendered")
    assert planned


def test_every_golden_plan_validates_against_the_contract(goldens: dict[Path, str]) -> None:
    for path, content in goldens.items():
        if path.suffix != ".json":
            continue
        problems = plan_problems(json.loads(content))
        assert problems == [], f"{path.name}: " + "\n".join(str(p) for p in problems)


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
    original = json.loads(goldens[GOLDEN / "plan" / "typical.json"])

    assert GOLDEN not in edited.parents, "a plan that is wrong on purpose is not a golden"
    assert document["plan_id"] == original["plan_id"]
    assert document["parameters"][0]["value"] != original["parameters"][0]["value"]


def test_every_golden_is_ascii(goldens: dict[Path, str]) -> None:
    """These are read in terminals and diffed on machines that disagree about encodings."""
    for path, content in goldens.items():
        assert content.isascii(), path.name
