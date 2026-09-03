"""Reading a facts document: what is folded away, what is refused, and how loudly.

Facts are the input everything else is built on. A plan sized against a number that was
wrong is a plan that looks entirely reasonable and is not, which is why a host that
contradicts itself is refused rather than worked around.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from basewright.facts import InvalidFactsError, MissingFactsError, load_facts, normalize
from basewright.report.problems import Problem

ROOT = Path(__file__).resolve().parents[2]
HOSTS = ROOT / "test" / "fixtures" / "hosts"


def document(name: str = "typical") -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((HOSTS / f"{name}.json").read_text(encoding="utf-8"))
    return loaded


def refuse(changed: dict[str, Any]) -> list[Problem]:
    with pytest.raises(InvalidFactsError) as raised:
        normalize(changed)
    return raised.value.problems


def located(problems: list[Problem]) -> list[str]:
    return [problem.location for problem in problems]


# ------------------------------------------------------------------------ canonicalizing


@pytest.mark.parametrize(
    ("reported", "canonical"),
    [
        ("x86_64", "x86_64"),
        ("amd64", "x86_64"),
        ("aarch64", "aarch64"),
        ("arm64", "aarch64"),
        ("ppc64le", "ppc64le"),
        ("s390x", "s390x"),
    ],
)
def test_both_spellings_of_a_machine_become_one(reported: str, canonical: str) -> None:
    """Which spelling a collector reports is not something it should have to ask us."""
    changed = document()
    changed["arch"] = reported

    assert normalize(changed).arch == canonical


def test_capitalisation_is_folded_away() -> None:
    """A comparison that fails on capitalisation is a comparison that fails at 3am."""
    changed = document()
    changed["os"]["family"] = "Debian"
    changed["os"]["distro"] = " Ubuntu "
    changed["arch"] = "AMD64"

    facts = normalize(changed)

    assert facts.os.family == "debian"
    assert facts.os.distro == "ubuntu"
    assert facts.arch == "x86_64"


def test_folding_does_not_alter_the_document_it_was_given() -> None:
    """Normalizing is reading, not editing. A caller's document is theirs."""
    original = document()
    original["arch"] = "amd64"
    before = json.dumps(original, sort_keys=True)

    normalize(original)

    assert json.dumps(original, sort_keys=True) == before


def test_a_fixture_on_disk_is_normalized_the_same_way() -> None:
    assert load_facts(HOSTS / "large.json").arch == "x86_64"
    assert load_facts(HOSTS / "rocky.json").arch == "aarch64"


# --------------------------------------------------------------------------- refusing


def test_a_document_that_is_not_there() -> None:
    with pytest.raises(MissingFactsError):
        load_facts(HOSTS / "nowhere.json")


def test_a_document_that_is_not_json(tmp_path: Path) -> None:
    broken = tmp_path / "facts.json"
    broken.write_text('{"schema_version": ', encoding="utf-8")

    with pytest.raises(InvalidFactsError) as raised:
        load_facts(broken)

    assert raised.value.problems[0].message == "is not valid JSON"
    assert raised.value.problems[0].hint


def test_a_document_that_is_not_a_mapping() -> None:
    problems = refuse([])  # type: ignore[arg-type]

    assert problems[0].message.startswith("is list, not a mapping")


def test_an_unknown_key_is_refused_rather_than_ignored() -> None:
    """A fact the core does not read is a fact somebody believes is being acted on."""
    changed = document()
    changed["selinux"] = "enforcing"

    problems = refuse(changed)

    assert located(problems) == ["selinux"]
    assert "closed" in problems[0].hint


def test_a_missing_section_a_blocking_rule_needs_is_refused() -> None:
    """A block gate never runs on absent data, so its facts are not optional."""
    changed = document()
    del changed["privileges"]

    problems = refuse(changed)

    assert located(problems) == ["privileges"]


def test_an_architecture_nobody_ships_for_is_refused() -> None:
    changed = document()
    changed["arch"] = "riscv64"

    problems = refuse(changed)

    assert located(problems) == ["arch"]
    assert "x86_64" in problems[0].message


# ----------------------------------------------------- refusing: a machine that cannot be


def test_a_mount_cannot_have_more_free_space_than_it_has() -> None:
    changed = document()
    changed["mounts"][1]["free_bytes"] = changed["mounts"][1]["total_bytes"] * 2

    problems = refuse(changed)

    assert located(problems) == ["mounts[1].free_bytes"]
    assert "cannot have more space free than it has" in problems[0].hint


def test_two_filesystems_cannot_be_mounted_in_the_same_place() -> None:
    """Longest-prefix matching has to have one answer, or it has an arbitrary one."""
    changed = document()
    changed["mounts"].append(dict(changed["mounts"][0]))

    problems = refuse(changed)

    assert located(problems) == ["mounts[3].path"]


def test_a_host_cannot_have_more_memory_available_than_installed() -> None:
    changed = document()
    changed["memory"]["available_bytes"] = changed["memory"]["total_bytes"] + 1

    problems = refuse(changed)

    assert located(problems) == ["memory.available_bytes"]


def test_a_processor_cannot_run_fewer_threads_than_it_has_cores() -> None:
    changed = document()
    changed["cpu"]["threads"] = 1

    problems = refuse(changed)

    assert located(problems) == ["cpu.threads"]
    assert "wrong order" in problems[0].hint


def test_every_contradiction_is_reported_at_once() -> None:
    """One problem per run is how a collector takes a day to fix."""
    changed = document()
    changed["cpu"]["threads"] = 1
    changed["memory"]["available_bytes"] = changed["memory"]["total_bytes"] + 1
    changed["mounts"][0]["free_bytes"] = changed["mounts"][0]["total_bytes"] * 2

    problems = refuse(changed)

    assert len(problems) == 3


def test_the_refusal_reads_like_the_one_a_bad_profile_gets() -> None:
    changed = document()
    changed["cpu"]["threads"] = 1

    with pytest.raises(InvalidFactsError) as raised:
        normalize(changed, source=Path("facts.json"))

    report = raised.value.report()
    assert "is not a valid facts document -- 1 problem." in report
    assert "cpu.threads" in report
    assert "->" in report


def test_the_refusal_speaks_in_units_a_person_reads() -> None:
    """32000000000 and 32.0 GiB are the same number, and only one is a sentence."""
    changed = document()
    changed["memory"]["available_bytes"] = changed["memory"]["total_bytes"] + 1

    problems = refuse(changed)

    assert "GiB" in problems[0].message
