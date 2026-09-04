"""Whether the host is still the machine a plan was built from.

Apply is the step that changes a machine, so it is the step that has to look before it
does. What makes this hard is not noticing a difference -- it is deciding which differences
matter. A check that refuses on any of them refuses every second run and gets turned off;
one that refuses on none of them is decoration.

So the tests here are as much about what is *not* drift as about what is.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from basewright.bridge import drifted
from basewright.drift import UNCHECKED, differences

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "test" / "golden" / "postgresql" / "plan" / "typical.json"
HOSTS = ROOT / "test" / "fixtures" / "hosts"


@pytest.fixture
def planned() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(PLAN.read_text(encoding="utf-8"))
    host: dict[str, Any] = document["host"]
    return host


def changed(planned: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """The same host, with something about it different."""
    observed = copy.deepcopy(planned)
    for path, value in overrides.items():
        target = observed
        *parents, leaf = path.split("__")
        for part in parents:
            target = target[part]
        target[leaf] = value
    return observed


def mount(planned: dict[str, Any], path: str, **overrides: Any) -> dict[str, Any]:
    observed = copy.deepcopy(planned)
    entry = next(item for item in observed["storage"] if item["mount"] == path)
    entry.update(overrides)
    return observed


# ------------------------------------------------------------------ the same machine


def test_the_machine_it_was_built_from_has_not_drifted(planned: dict[str, Any]) -> None:
    assert differences(planned, copy.deepcopy(planned)) == []


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"os__kernel": "6.8.0-99-generic"}, id="a kernel patch"),
        pytest.param({"os__pretty_name": "Ubuntu 24.04.3 LTS"}, id="a point release"),
        pytest.param({"cpu__model": "Xeon Gold 6338"}, id="a model string"),
        pytest.param({"memory__swap_bytes": 0}, id="swap turned off"),
    ],
)
def test_what_changes_on_its_own_is_not_drift(
    planned: dict[str, Any], overrides: dict[str, Any]
) -> None:
    """None of these was read by a rule reaching a verdict or computing a value. A check
    that refused on them would refuse after every patch window, which is how a drift check
    stops being run."""
    assert differences(planned, changed(planned, **overrides)) == []


def test_a_host_given_more_of_something_still_fits_the_plan(planned: dict[str, Any]) -> None:
    """Sizing was computed from what the machine had. More of it is not a reason to refuse
    to configure the instance that was sized for less."""
    grown = changed(planned, memory__total_bytes=planned["memory"]["total_bytes"] * 2)
    grown = changed(grown, cpu__cores=planned["cpu"]["cores"] + 8)

    assert differences(planned, grown) == []


def test_free_space_is_not_compared_at_all(planned: dict[str, Any]) -> None:
    """The interesting omission. Apply consumes free space -- installing the packages and
    creating the instance is what makes a filesystem smaller -- so a second run comparing
    against the plan's numbers would report its own work as drift and refuse to be
    idempotent. It is checked once, by a blocking gate, before the plan exists."""
    emptier = mount(planned, "/var/lib", free_bytes=1024)

    assert differences(planned, emptier) == []


# --------------------------------------------------------------- a different machine


@pytest.mark.parametrize(
    "overrides,named",
    [
        pytest.param({"os__family": "rhel"}, "os.family", id="family"),
        pytest.param({"os__distro": "debian"}, "os.distro", id="distribution"),
        pytest.param({"os__version": "22.04"}, "os.version", id="version"),
        pytest.param({"arch": "aarch64"}, "arch", id="architecture"),
    ],
)
def test_a_machine_that_is_something_else_now_is_drift(
    planned: dict[str, Any], overrides: dict[str, Any], named: str
) -> None:
    """Every one of these decided which engine version is supported at all."""
    found = differences(planned, changed(planned, **overrides))

    assert [difference.fact for difference in found] == [named]
    assert found[0].consequence


@pytest.mark.parametrize("fact", ["cpu__cores", "memory__total_bytes"])
def test_a_machine_with_less_than_it_had_is_drift(planned: dict[str, Any], fact: str) -> None:
    """Applying a plan sized for a larger machine onto a smaller one is the failure this
    exists to catch, and it is silent: the instance starts, and then does not."""
    shrunk = changed(planned, **{fact: 2})
    found = differences(planned, shrunk)

    assert len(found) == 1
    assert "less" in found[0].consequence


def test_a_filesystem_the_plan_placed_a_path_on_and_is_gone_is_drift(
    planned: dict[str, Any],
) -> None:
    """The loudest of them. A path created on a filesystem that is not mounted lands on
    whatever covers the directory instead, which is how a data directory ends up on the
    root volume."""
    unmounted = copy.deepcopy(planned)
    unmounted["storage"] = [entry for entry in unmounted["storage"] if entry["mount"] != "/backup"]
    found = differences(planned, unmounted)

    assert [difference.fact for difference in found] == ["storage /backup"]
    assert found[0].observed == "not mounted"


def test_a_filesystem_that_is_a_different_filesystem_now_is_drift(
    planned: dict[str, Any],
) -> None:
    found = differences(planned, mount(planned, "/backup", filesystem="btrfs"))

    assert len(found) == 1
    assert found[0].planned == "xfs"
    assert found[0].observed == "btrfs"


def test_storage_that_has_stopped_spinning_is_drift(planned: dict[str, Any]) -> None:
    """Two sizing rules cost random reads differently on it, so parameters in this plan
    were sized for storage this host no longer has."""
    found = differences(planned, mount(planned, "/backup", rotational=False))

    assert len(found) == 1
    assert (found[0].planned, found[0].observed) == ("rotational", "solid state")


def test_a_difference_reads_as_a_sentence_somebody_can_act_on(planned: dict[str, Any]) -> None:
    found = differences(planned, changed(planned, arch="aarch64"))

    assert str(found[0]).startswith("arch: planned x86_64, now aarch64 -- ")


def test_memory_is_reported_in_units_a_person_reads(planned: dict[str, Any]) -> None:
    found = differences(planned, changed(planned, memory__total_bytes=8 * 1024**3))

    assert (found[0].planned, found[0].observed) == ("32.0 GiB", "8.0 GiB")


# ------------------------------------------------------------------- what it cannot see


def test_what_a_plan_does_not_carry_is_written_down_rather_than_implied() -> None:
    """The honest half of what this does. A drift check is only as wide as the record it
    compares against, and somebody relying on it is entitled to know where it stops."""
    assert UNCHECKED
    assert all(len(limit) > 40 for limit in UNCHECKED)
    assert any("services" in limit for limit in UNCHECKED)
    assert any("ports" in limit for limit in UNCHECKED)


def test_a_fact_the_plan_never_recorded_cannot_be_missed(planned: dict[str, Any]) -> None:
    """Not a defect: it is the shape of the constraint. Apply reads the plan and nothing
    else, so what it can notice is exactly what the plan wrote down."""
    assert "services" not in planned
    assert "network" not in planned


# ------------------------------------------------------------------------- the bridge


def test_the_bridge_reads_a_collected_document_through_the_contract() -> None:
    """Ansible hands over what a host reported; what counts as drift is decided here."""
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    collected = json.loads((HOSTS / "collected.json").read_text(encoding="utf-8"))

    reported = drifted(plan, collected)

    assert reported, "a Debian container is not the Ubuntu host this plan was built from"
    assert all(isinstance(line, str) for line in reported)


def test_the_bridge_says_nothing_when_the_host_is_the_one_the_plan_describes() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    same = json.loads((HOSTS / "typical.json").read_text(encoding="utf-8"))

    assert drifted(plan, same) == []
