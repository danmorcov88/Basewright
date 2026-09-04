"""The pictures have to describe the thing that exists.

A diagram is the part of the documentation nobody rereads when the format changes, which
is exactly why it is checked mechanically rather than by intention. The renderer holds one
list of the files a profile is made of and the loader holds another; if they ever disagree,
the build says so rather than the README quietly describing a format nobody ships.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from basewright.profiles import load_profile
from basewright.profiles.schema import PROFILE_FILES, schema_name_for
from basewright.schema import schema_directory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from render_assets import (  # noqa: E402
    PLAN_ANATOMY,
    PROFILE_ANATOMY,
    SIZING_JOURNEY,
    SIZING_JOURNEY_FOOTER,
    SIZING_JOURNEY_HOST,
    SIZING_JOURNEY_PARAMETER,
)


def test_the_diagram_lists_the_files_a_profile_is_made_of() -> None:
    drawn = tuple(name for name, _, _ in PROFILE_ANATOMY)

    assert drawn == PROFILE_FILES, (
        "The profile anatomy diagram in tools/render_assets.py lists a different set of "
        "files than the loader reads. One of the two is out of date."
    )


def test_every_file_the_diagram_draws_is_validated() -> None:
    """A file in the picture with no schema is a file nothing checks."""
    for name, _, _ in PROFILE_ANATOMY:
        assert (schema_directory() / schema_name_for(name)).is_file()


def test_every_file_the_diagram_draws_says_who_reads_it() -> None:
    """A file whose consumer nobody can name is a file with no reason to exist."""
    for name, declares, reader in PROFILE_ANATOMY:
        assert declares, f"{name} is drawn without saying what it declares"
        assert reader, f"{name} is drawn without saying which step reads it"


# ------------------------------------------------------------- the picture of a plan


def test_the_diagram_lists_every_section_a_plan_carries() -> None:
    """This contract is frozen, so a picture that describes a different one is worse
    here than anywhere else in the documentation.

    Every section a plan can carry is drawn, not only the ones it must: a reader working
    out whether apply has what it needs is reading this for the whole list. What the two
    assertions keep apart is that every drawn section exists, and that the required ones
    are drawn in the order the schema states them."""
    schema = json.loads((schema_directory() / "plan.schema.json").read_text(encoding="utf-8"))
    drawn = [name for name, _, _ in PLAN_ANATOMY]

    assert set(drawn) == set(schema["properties"])
    assert [name for name in drawn if name in schema["required"]] == schema["required"]


def test_a_section_the_schema_does_not_require_is_one_a_profile_may_omit() -> None:
    """The only optional section is initialization, and it is optional because an engine
    whose packages leave a running instance behind them has nothing to create. A second
    optional section arriving without anybody deciding it should be is what this catches."""
    schema = json.loads((schema_directory() / "plan.schema.json").read_text(encoding="utf-8"))
    optional = set(schema["properties"]) - set(schema["required"])

    assert optional == {"initialization"}


def test_every_section_the_diagram_draws_says_who_reads_it() -> None:
    for name, carries, reader in PLAN_ANATOMY:
        assert carries, f"{name} is drawn without saying what it carries"
        assert reader, f"{name} is drawn without saying which step reads it"


# ------------------------------------------------------ the journey of one real value


def test_the_journey_ends_where_the_golden_plan_says_it_does() -> None:
    """The numbers in the picture are the ones the pipeline produces, or it is fiction."""
    plan = json.loads(
        (ROOT / "test" / "golden" / "exampledb" / "plan" / f"{SIZING_JOURNEY_HOST}.json").read_text(
            encoding="utf-8"
        )
    )
    parameter = next(
        entry for entry in plan["parameters"] if entry["parameter"] == SIZING_JOURNEY_PARAMETER
    )
    stages = {stage: value for stage, value, _ in SIZING_JOURNEY}

    assert stages["bounded"] == parameter["display"]
    assert parameter["bounded_by"] == "max"
    assert stages["in the plan"] == f"{parameter['parameter']} {parameter['display']}"
    assert str(parameter["value"]) in " ".join(SIZING_JOURNEY_FOOTER), (
        "The caption names the raw number the plan carries. If the value changed, the "
        "caption is now claiming something the artifact does not say."
    )


def test_the_journey_starts_from_the_rule_the_profile_actually_wrote() -> None:
    profile = load_profile(ROOT / "test" / "fixtures" / "profiles" / "exampledb")
    rule = next(entry for entry in profile.sizing if entry.parameter == SIZING_JOURNEY_PARAMETER)
    stages = {stage: value for stage, value, _ in SIZING_JOURNEY}

    assert stages["the rule"] == rule.expr
