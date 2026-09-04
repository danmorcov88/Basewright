"""What a plan says for itself.

The rendering is checked against a plan the pipeline really produced, because that is what
it will be asked to render: a file, months later, handed to somebody who was not there
when it was made. Rendering from a hand-built dictionary would prove only that the
renderer agrees with the test's idea of a plan.

Three properties are load-bearing and are checked on every fixture. It fits 88 columns,
because it is read in a terminal and in a task log. It is ASCII, because it is also
captured into a documentation image on a machine that may not agree with this one about
console encodings. And every value carries the rule that produced it and that rule's
reasoning, which is the whole claim the artifact makes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from basewright.report.plan import render_plan
from basewright.report.problems import REPORT_WIDTH

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / "test" / "golden" / "exampledb" / "plan"

#: Every fixture host that produces a plan, and what each of them is here to show.
FIXTURES: tuple[tuple[str, str], ...] = (
    ("typical", "the machine the documentation is written about"),
    ("large", "a value held at its ceiling, and one past an advisory"),
)


def plan(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((PLANS / f"{name}.json").read_text(encoding="utf-8"))
    return document


@pytest.fixture(scope="module")
def typical() -> dict[str, Any]:
    return plan("typical")


@pytest.fixture(scope="module")
def rendering(typical: dict[str, Any]) -> str:
    return render_plan(typical)


# --------------------------------------------------------------------------- the shape


@pytest.mark.parametrize("name", [name for name, _ in FIXTURES])
def test_it_fits_the_width_every_report_here_is_read_at(name: str) -> None:
    for line in render_plan(plan(name)).splitlines():
        assert len(line) <= REPORT_WIDTH, line


@pytest.mark.parametrize("name", [name for name, _ in FIXTURES])
def test_it_is_ascii(name: str) -> None:
    """A non-ASCII character makes the documentation image differ between machines."""
    assert render_plan(plan(name)).isascii()


@pytest.mark.parametrize("name", [name for name, _ in FIXTURES])
def test_every_section_is_present(name: str) -> None:
    rendered = render_plan(plan(name))

    for section in (
        "BASEWRIGHT PLAN",
        "REQUEST",
        "HOST",
        "PREFLIGHT",
        "PARAMETERS",
        "LAYOUT",
        "CHANGES apply WOULD MAKE",
        "SECRETS",
        "RESULT",
    ):
        assert section in rendered


def test_the_header_names_the_plan_and_when_it_was_made(
    rendering: str, typical: dict[str, Any]
) -> None:
    """The moment is here rather than only in the artifact: a plan attached to a change
    request is read by somebody who was not there when it was produced."""
    assert typical["request"]["host"] in rendering
    assert typical["plan_id"] in rendering
    assert typical["generated_at"] in rendering
    assert typical["tool_version"] in rendering


# ------------------------------------------------------------------ what it has to say


def test_every_parameter_carries_its_rule_and_its_reasoning(
    rendering: str, typical: dict[str, Any]
) -> None:
    """A number without a reason is the situation this project exists to end."""
    for parameter in typical["parameters"]:
        assert parameter["parameter"] in rendering
        assert parameter["display"] in rendering
        assert parameter["rule"] in rendering
        assert parameter["why"].split(".")[0] in " ".join(rendering.split())


def test_a_value_held_at_a_bound_says_so() -> None:
    rendered = render_plan(plan("large"))

    assert "held at its maximum" in rendered


def test_a_value_past_an_advisory_says_which_one() -> None:
    """It is permitted, and it is why somebody has to acknowledge this plan."""
    rendered = render_plan(plan("large"))

    assert "above the 16 this rule advises" in rendered


def test_a_version_nobody_chose_is_labelled_as_the_default(rendering: str) -> None:
    """A version somebody named and a version nobody named are not the same decision."""
    assert "(profile default)" in rendering


def test_only_the_rules_that_did_not_pass_are_named(
    rendering: str, typical: dict[str, Any]
) -> None:
    """The counts say how many agreed. Naming eighteen of them buries the four that did
    not under the ones nobody has to act on."""
    summary = typical["preflight"]["summary"]
    assert f"{summary['pass']} pass" in rendering

    passed = [r for r in typical["preflight"]["results"] if r["outcome"] == "pass"]
    for result in passed:
        assert result["id"] not in rendering
    for result in typical["preflight"]["results"]:
        if result["outcome"] != "pass":
            assert result["id"] in rendering


def test_a_warning_carries_what_would_change_it(rendering: str) -> None:
    assert "-> Set vm.swappiness to 10 or below" in " ".join(rendering.split())


def test_the_layout_says_who_owns_each_path(rendering: str, typical: dict[str, Any]) -> None:
    for entry in typical["layout"]["paths"]:
        assert entry["path"] in rendering
        assert entry["mode"] in rendering
    assert "exampledb:exampledb" in rendering


def test_the_changes_are_marked_by_what_they_do(rendering: str) -> None:
    """Add and modify. There is no third marker, because apply does no third thing."""
    assert "  + install" in rendering
    assert "  ~ set vm.swappiness 60 -> 10" in rendering
    assert "Nothing existing is removed" in rendering


def test_a_secret_is_named_and_located_and_never_carried(
    rendering: str, typical: dict[str, Any]
) -> None:
    secret = typical["secrets"][0]

    assert secret["name"] in rendering
    assert secret["location"] in rendering
    assert "nowhere to put a value" in " ".join(rendering.split())


def test_the_verdict_is_the_last_thing_read(rendering: str) -> None:
    last = rendering.splitlines()[-1]

    assert last.startswith("RESULT")
    assert "acknowledgement" in last


def test_a_plan_with_nothing_to_acknowledge_says_that_instead(
    typical: dict[str, Any],
) -> None:
    quiet = json.loads(json.dumps(typical))
    quiet["result"] = {
        "applicable": True,
        "warnings": 0,
        "warnings_require_acknowledgement": False,
    }
    quiet["preflight"]["summary"] = {"pass": 23, "warn": 0, "block": 0, "skip": 0}
    quiet["preflight"]["results"] = []

    rendered = render_plan(quiet)

    assert "nothing to acknowledge" in rendered
    assert "every rule agreed" in rendered


def test_a_plan_needing_no_secrets_says_so(typical: dict[str, Any]) -> None:
    """An empty list is a statement, not a silence."""
    bare = json.loads(json.dumps(typical))
    bare["secrets"] = []

    assert "this instance needs none" in render_plan(bare)


def test_a_host_that_reported_no_clock_is_simply_not_described(
    typical: dict[str, Any],
) -> None:
    """An optional fact that was not collected is absent, not guessed at."""
    silent = json.loads(json.dumps(typical))
    del silent["host"]["time_sync"]

    assert "time sync" not in render_plan(silent)


# --------------------------------------------------------- what creating it takes

#: The plan of an engine that has something to create. The fixture profile has nothing, so
#: the rendering of this section is read off the shipped one -- which is the same document
#: read by the same code, and the reason there is only one rendering.
POSTGRESQL_PLAN = ROOT / "test" / "golden" / "postgresql" / "plan" / "typical.json"


@pytest.fixture(scope="module")
def creating() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(POSTGRESQL_PLAN.read_text(encoding="utf-8"))
    return document


def test_every_choice_made_creating_the_instance_carries_its_reasoning(
    creating: dict[str, Any],
) -> None:
    """This is the one section describing something a second run cannot put right, so its
    reasoning is worth more than any other section's, not less."""
    rendered = render_plan(creating)
    section = rendered[rendered.index("INITIALIZATION") : rendered.index("CHANGES apply")]

    for setting in creating["initialization"]["settings"]:
        assert setting["name"] in section
        assert setting["why"].split(".")[0] in " ".join(section.split())


def test_the_locale_is_shown_beside_the_choices_made_with_it(
    creating: dict[str, Any],
) -> None:
    rendered = render_plan(creating)
    section = rendered[rendered.index("INITIALIZATION") : rendered.index("CHANGES apply")]

    assert creating["initialization"]["locale"] in section


def test_a_boolean_choice_reads_as_a_word_rather_than_as_python(
    creating: dict[str, Any],
) -> None:
    """`True` with a capital letter is a language showing through a document written for
    somebody who does not use it."""
    rendered = render_plan(creating)

    assert "True" not in rendered
    assert "data_checksums    true" in rendered


def test_a_plan_that_creates_nothing_has_no_heading_over_nothing(
    typical: dict[str, Any],
) -> None:
    """The fixture engine's packages leave a running instance behind them. An empty
    section would read as something the plan failed to say."""
    assert "initialization" not in typical
    assert "INITIALIZATION" not in render_plan(typical)
