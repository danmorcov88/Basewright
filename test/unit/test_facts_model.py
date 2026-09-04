"""The questions a rule asks of a host, over the five fixture machines.

Each fixture exists to make something specific true, and the tests below name which. The
one that matters most is mount resolution: "which filesystem carries this path" has
exactly one right answer and several plausible wrong ones, and every disk gate, every
free-space threshold and the mount a plan reports all depend on getting it right.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from basewright.facts import HostFacts, Mount, load_facts
from basewright.planner.schema import plan_problems
from basewright.units import parse_bytes

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PLAN = ROOT / "test" / "golden" / "exampledb" / "plan" / "typical.json"
HOSTS = ROOT / "test" / "fixtures" / "hosts"

#: Every fixture host, and the one thing each of them is for.
FIXTURES: tuple[tuple[str, str], ...] = (
    ("typical", "the machine the documentation is written about"),
    ("small", "too little of everything, on one rotational disk"),
    ("large", "nested mounts, a read-only one, and an architecture synonym"),
    ("crowded", "a full backup mount, the port taken, something already installed"),
    ("rocky", "another family, another architecture, and no backup mount at all"),
)


def host(name: str) -> HostFacts:
    return load_facts(HOSTS / f"{name}.json")


@pytest.fixture
def typical() -> HostFacts:
    return host("typical")


@pytest.fixture
def large() -> HostFacts:
    return host("large")


@pytest.mark.parametrize(("name", "purpose"), FIXTURES, ids=[name for name, _ in FIXTURES])
def test_every_fixture_host_loads(name: str, purpose: str) -> None:
    assert host(name).host.endswith(".invalid"), purpose


def test_the_fixtures_cover_more_than_one_kind_of_machine() -> None:
    """Five copies of one machine would prove the model works on that machine."""
    hosts = [host(name) for name, _ in FIXTURES]

    assert len({facts.os.family for facts in hosts}) > 1
    assert len({facts.arch for facts in hosts}) > 1
    assert len({facts.cpu.cores for facts in hosts}) > 2


# --------------------------------------------------------------- which mount carries what


def test_the_deepest_mount_wins(large: HostFacts) -> None:
    """Four mounts are prefixes of this path, and only the deepest one is the answer."""
    mount = large.mount_for("/var/lib/basewright/main/data")

    assert mount is not None
    assert mount.path == "/var/lib/basewright"


def test_a_path_under_no_special_mount_lands_on_root(typical: HostFacts) -> None:
    mount = typical.mount_for("/etc/somewhere")

    assert mount is not None
    assert mount.path == "/"


def test_a_mount_is_not_a_prefix_of_a_longer_name(typical: HostFacts) -> None:
    """The failure this guards: /var matching /variable, and a threshold checked on the
    wrong filesystem while every number in the report looks plausible."""
    mounts = (Mount(path="/var", filesystem="ext4", total_bytes=10, free_bytes=5),)

    assert mounts[0].carries("/var/lib")
    assert not mounts[0].carries("/variable/lib")


def test_a_host_with_no_backup_mount_says_so(typical: HostFacts) -> None:
    rocky = host("rocky")

    assert typical.mount_for("/backup") is not None
    assert rocky.mount_for("/backup") is not None
    assert rocky.mount_for("/backup").path == "/"  # type: ignore[union-attr]


def test_free_space_is_answered_per_path(typical: HostFacts) -> None:
    assert typical.free_bytes_for("/var/lib/x/data") == parse_bytes("512GiB")
    assert typical.free_bytes_for("/backup/x") == parse_bytes("2TiB")


def test_paths_that_share_a_mount_are_known_to(typical: HostFacts, large: HostFacts) -> None:
    """Separate mounts for data and the journal is the whole point of asking."""
    assert typical.shares_mount_with("/var/lib/x/data", "/var/lib/x/journal")
    assert not typical.shares_mount_with("/var/lib/x/data", "/backup/x")
    assert not large.shares_mount_with("/var/lib/basewright/x/data", "/var/log/x")


def test_a_read_only_mount_is_visible(large: HostFacts) -> None:
    """A planned path on a read-only mount is a refusal, not a surprise at apply time."""
    mount = large.mount_for("/mnt/readonly")

    assert mount is not None
    assert mount.read_only
    assert not large.mounts[0].read_only


def test_trailing_separators_do_not_change_the_answer(typical: HostFacts) -> None:
    plain = typical.mount_for("/var/lib/x")
    trailing = typical.mount_for("/var/lib/x/")

    assert plain is not None
    assert trailing is not None
    assert plain.path == trailing.path


# ------------------------------------------------------------------- the other questions


def test_a_port_already_listening_is_found(typical: HostFacts) -> None:
    crowded = host("crowded")

    assert typical.port_in_use(6432) is None
    assert crowded.port_in_use(6432) is not None
    assert crowded.port_in_use(6432).process == "exampledb"  # type: ignore[union-attr]


def test_a_port_is_only_taken_on_the_protocol_it_is_taken_on(typical: HostFacts) -> None:
    assert typical.port_in_use(22, "tcp") is not None
    assert typical.port_in_use(22, "udp") is None


def test_a_locale_is_looked_for_in_the_spelling_the_c_library_uses(typical: HostFacts) -> None:
    """An engine initialized with a locale the host does not have fails at the last moment,
    so this rule blocks and cannot be overridden -- which makes a false refusal here the
    most expensive kind of wrong. `locale -a` normalizes the codeset when it prints, so a
    locale generated as en_US.UTF-8 is listed as en_US.utf8 on every Debian and Ubuntu
    host there is. Comparing the two strings refused a machine that had exactly what was
    asked for, and a real container is what found it."""
    assert typical.locale_present("en_US.UTF-8")
    assert typical.locale_present("en_US.utf8")
    assert typical.locale_present("en_US.Utf-8")
    assert not host("small").locale_present("en_US.UTF-8")


def test_a_locale_that_differs_by_more_than_spelling_is_a_different_locale(
    typical: HostFacts,
) -> None:
    """Only the codeset is normalized, because only the codeset is what the library
    rewrites. A territory is not a spelling variation."""
    assert not typical.locale_present("en_GB.UTF-8")
    assert not typical.locale_present("en_US.ISO-8859-1")
    assert not typical.locale_present("en_US.UTF-8@euro")


def test_an_installed_service_is_found_by_the_name_a_profile_would_use() -> None:
    crowded = host("crowded")

    installed = crowded.service_named("exampledb")
    assert installed is not None
    assert installed.state == "running"
    assert crowded.service_named("something-else") is None


def test_a_firewall_admits_a_port_or_does_not() -> None:
    crowded = host("crowded")
    large = host("large")

    assert crowded.firewall is not None
    assert not crowded.firewall.admits(6432)
    assert crowded.firewall.admits(22)

    assert large.firewall is not None
    assert large.firewall.admits(6432), "an inactive firewall admits everything"


def test_sections_a_host_did_not_report_are_absent_rather_than_invented() -> None:
    """A warning rule can be skipped. A rule guessing at a missing fact cannot be reviewed."""
    small = host("small")

    assert small.time_sync is None
    assert small.firewall is None
    assert small.kernel is not None


def test_an_undetermined_rotational_flag_is_not_false() -> None:
    """Unknown and "not rotational" are different answers, and only one of them is a fact."""
    rocky = host("rocky")

    var = rocky.mount_for("/var/lib")
    assert var is not None
    assert var.rotational is None
    assert rocky.mounts[0].rotational is False


# ------------------------------------------------------------- the shape a plan carries


@pytest.mark.parametrize("name", [name for name, _ in FIXTURES])
def test_the_host_section_of_a_plan_validates(name: str) -> None:
    """The two contracts have to agree, and the honest way to ask is to build one.

    Comparing the two schema documents structurally would pass while meaning nothing. This
    takes a real host, renders it the way the planner will, and checks the plan schema
    accepts it.
    """
    section = host(name).plan_section()

    problems = plan_problems(_plan_around(section))

    assert problems == [], "\n".join(str(problem) for problem in problems)


def test_a_fact_that_was_not_observed_is_left_out_rather_than_nulled() -> None:
    """The plan schema is closed and its optional fields are optional. Null would claim
    the question was asked and answered with nothing."""
    section = host("rocky").plan_section()

    assert "codename" not in section["os"]
    assert "rotational" not in section["storage"][1]
    assert section["storage"][0]["rotational"] is False


def _plan_around(section: dict[str, object]) -> dict[str, object]:
    """A real plan with this host's section dropped into it.

    Written this way rather than as a hand-made minimal document, because a hand-made one
    only proves that the host section satisfies whatever the schema said when it was
    typed. Borrowing a plan the pipeline actually produced means the two contracts are
    held together by something that would notice if either moved.
    """
    plan: dict[str, object] = json.loads(GOLDEN_PLAN.read_text(encoding="utf-8"))
    plan["host"] = section
    return plan
