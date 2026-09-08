"""Where a plan lives between the person who produces it and the person who applies it.

The store exists for one sentence in §12: `Apply` can be run by somebody other than whoever
produced the plan. Everything here is about that sentence holding -- an id survives being
copied out of a task log and back into a survey field, and the things that arrive with it
are typed by a person and therefore checked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from basewright.bridge import pointer
from basewright.store import (
    StoreError,
    applied,
    instance_path,
    keep,
    known,
    plan_path,
    read,
)

ROOT = Path(__file__).resolve().parents[2]
APPLIED = ROOT / "test" / "fixtures" / "plan" / "applied.json"
FIXTURE_STORE = ROOT / "test" / "fixtures" / "store"


@pytest.fixture(scope="module")
def rendered() -> str:
    return APPLIED.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def plan(rendered: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(rendered)
    return document


# ------------------------------------------------------------------- keeping and finding


def test_a_plan_is_kept_under_its_own_id(
    tmp_path: Path, plan: dict[str, Any], rendered: str
) -> None:
    """The name and the checksum are the same string (ADR-0017), which is what makes an id
    worth passing between two people."""
    written = keep(tmp_path, plan, rendered)

    assert written == plan_path(tmp_path, plan["plan_id"])
    assert written.read_text(encoding="utf-8") == rendered


def test_what_comes_back_is_byte_for_byte_what_went_in(
    tmp_path: Path, plan: dict[str, Any], rendered: str
) -> None:
    """Not an equivalent document. A plan is named after a digest of its content, so the
    artifact read later has to be the one the digest was taken over -- a re-serialization
    that differed by a space would still be a plan and would no longer be *this* plan."""
    keep(tmp_path, plan, rendered)

    assert read(tmp_path, plan["plan_id"]) == rendered


def test_keeping_a_plan_that_is_already_there_changes_nothing(
    tmp_path: Path, plan: dict[str, Any], rendered: str
) -> None:
    """The id is the digest, so a second write of the same id is the same bytes. Deciding
    what to do about a collision that cannot happen would be inventing a problem."""
    first = keep(tmp_path, plan, rendered)
    again = keep(tmp_path, plan, rendered)

    assert first == again
    assert again.read_text(encoding="utf-8") == rendered


def test_a_plan_the_store_has_not_got_says_what_it_does_have(
    tmp_path: Path, plan: dict[str, Any], rendered: str
) -> None:
    """The failure this message is read after is almost always a typo or the wrong store,
    and the two look identical until somebody sees what the store actually holds."""
    keep(tmp_path, plan, rendered)

    with pytest.raises(StoreError) as refused:
        read(tmp_path, "000000000000")
    assert plan["plan_id"] in str(refused.value)


def test_an_empty_store_says_it_is_empty(tmp_path: Path) -> None:
    """Rather than listing nothing and leaving somebody to work out which it meant."""
    with pytest.raises(StoreError, match="holds no plans at all"):
        read(tmp_path, "000000000000")


def test_a_store_lists_what_it_holds(tmp_path: Path, plan: dict[str, Any], rendered: str) -> None:
    assert known(tmp_path) == []

    keep(tmp_path, plan, rendered)
    assert known(tmp_path) == [plan["plan_id"]]


# ----------------------------------------------------------------------- the pointer


def test_an_instance_points_at_the_plan_it_was_applied_from(tmp_path: Path) -> None:
    """One line, and the question it answers is which plan this instance is supposed to
    match now. Written by the playbook; this is the reading half."""
    destination = instance_path(tmp_path, "db-01.invalid", "main")
    destination.parent.mkdir(parents=True)
    destination.write_text("a67a746d7850\n", encoding="utf-8")

    assert applied(tmp_path, "db-01.invalid", "main") == "a67a746d7850"


def test_an_instance_nobody_applied_says_so_rather_than_guessing(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="does not say which plan"):
        applied(tmp_path, "db-01.invalid", "main")


def test_the_pointer_path_comes_out_of_the_plan(tmp_path: Path, plan: dict[str, Any]) -> None:
    """Apply reads the plan and nothing else, so the host and the instance the pointer is
    filed under are the ones the plan uses -- a pointer written under any other name is a
    pointer verify never finds."""
    expected = instance_path(tmp_path, plan["request"]["host"], plan["request"]["instance"])

    assert pointer(plan, str(tmp_path)) == str(expected)


# ------------------------------------------------------------ what a person typed in

#: Every one of these arrives from a survey field. The interesting input is not a wrong id
#: but one shaped like somewhere else on the filesystem.
TRAVERSALS = ("../../etc/passwd", "..", "/etc/passwd", "a/b", "", "UPPER", "x")


@pytest.mark.parametrize("given", TRAVERSALS)
def test_a_plan_id_that_could_name_somewhere_else_is_refused(tmp_path: Path, given: str) -> None:
    with pytest.raises(StoreError, match="not a plan id"):
        plan_path(tmp_path, given)


@pytest.mark.parametrize("given", ("../..", "a/b", "", ".hidden"))
def test_a_host_or_instance_that_could_name_somewhere_else_is_refused(
    tmp_path: Path, given: str
) -> None:
    with pytest.raises(StoreError):
        instance_path(tmp_path, given, "main")
    with pytest.raises(StoreError):
        instance_path(tmp_path, "db-01.invalid", given)


def test_a_refusal_says_the_shape_was_wrong_rather_than_tidying_it(tmp_path: Path) -> None:
    """Sanitizing a path into something it did not say is how a store ends up reading a file
    somebody did not ask for and reporting it as the one they did."""
    with pytest.raises(StoreError, match="refused rather than tidied"):
        plan_path(tmp_path, "../../etc/passwd")


# --------------------------------------------------------------- the committed fixture


def test_the_committed_store_holds_the_plan_that_was_really_applied() -> None:
    """Generated from the real plan by tools/render_goldens.py, so it cannot fall behind it.
    Committed because a refusal that names what the store *does* hold has to hold something
    somebody chose in order to be captured the same way twice."""
    plan = json.loads(APPLIED.read_text(encoding="utf-8"))

    assert known(FIXTURE_STORE) == [plan["plan_id"]]
    assert read(FIXTURE_STORE, plan["plan_id"]) == APPLIED.read_text(encoding="utf-8")


def test_the_committed_store_answers_the_question_the_verify_template_asks() -> None:
    """§12 gives that template a host and an instance name and no plan id."""
    plan = json.loads(APPLIED.read_text(encoding="utf-8"))
    request = plan["request"]

    assert applied(FIXTURE_STORE, request["host"], request["instance"]) == plan["plan_id"]
