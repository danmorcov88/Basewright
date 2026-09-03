"""The decision records have to be records, and the map of them has to be accurate.

Two failures are worth catching mechanically. A record that is added to `docs/adr/` and
never reaches the decision map leaves the picture quietly describing a smaller project
than the one that exists. And a record that skips its rejected alternatives is a
statement of what was chosen without the reasoning that makes it worth reading -- which
is the difference between a decision record and a note.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"

sys.path.insert(0, str(ROOT / "tools"))

from render_assets import DECISIONS  # noqa: E402

FILENAME = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")

#: Every record answers all four questions. A heading missing here means the record
#: states a position without the argument for it.
REQUIRED_SECTIONS = (
    "## Context",
    "## Decision",
    "## Consequences",
    "## Rejected alternatives",
)


def record_files() -> list[Path]:
    return sorted(path for path in ADR_DIR.glob("*.md") if FILENAME.match(path.name))


def record_numbers() -> list[str]:
    return [match.group(1) for path in record_files() if (match := FILENAME.match(path.name))]


def mapped_numbers() -> list[str]:
    return sorted(number for _, entries in DECISIONS for number, _ in entries)


def test_records_exist() -> None:
    """A check over an empty directory is a check that always passes."""
    assert record_files(), f"no decision records found in {ADR_DIR}"


def test_numbers_are_unique_and_contiguous() -> None:
    numbers = record_numbers()
    assert numbers == sorted(set(numbers)), "duplicate decision record numbers"
    expected = [f"{index:04d}" for index in range(1, len(numbers) + 1)]
    assert numbers == expected, "decision record numbers have a gap"


def test_every_record_is_on_the_decision_map() -> None:
    missing = sorted(set(record_numbers()) - set(mapped_numbers()))
    assert not missing, (
        f"records {missing} exist but are absent from DECISIONS in tools/render_assets.py, "
        "so the rendered decision map understates the project"
    )


def test_the_decision_map_invents_nothing() -> None:
    invented = sorted(set(mapped_numbers()) - set(record_numbers()))
    assert not invented, f"DECISIONS names records {invented} that do not exist in docs/adr/"


@pytest.mark.parametrize("path", record_files(), ids=lambda path: path.stem)
def test_record_is_a_record(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    missing = [section for section in REQUIRED_SECTIONS if section not in content]
    assert not missing, f"{path.name} is missing {missing}"


@pytest.mark.parametrize("path", record_files(), ids=lambda path: path.stem)
def test_record_declares_a_status(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    assert re.search(r"^\*\*Status:\*\* \w+ · \d{4}-\d{2}-\d{2}$", content, re.MULTILINE), (
        f"{path.name} has no status line of the form '**Status:** Accepted · YYYY-MM-DD'"
    )


@pytest.mark.parametrize("path", record_files(), ids=lambda path: path.stem)
def test_record_title_matches_its_number(path: Path) -> None:
    match = FILENAME.match(path.name)
    assert match is not None
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith(f"# ADR-{match.group(1)}: "), (
        f"{path.name} opens with {first_line!r}, which does not match its number"
    )
