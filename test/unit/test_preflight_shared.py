"""Both outcomes of every shared rule, and the skip where a rule has one.

The test policy admits no exceptions here: a gate ships with a test for both of its
outcomes. A rule tested only where it passes is a rule that could have been written
backwards, and nothing would say so until it declined to refuse a host it should have.

Each test varies one thing against a host and a profile that are otherwise fine, so a
failure names the rule that changed its mind rather than the fixture that was rebuilt.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from basewright.facts import load_facts
from basewright.facts.model import (
    Cpu,
    Firewall,
    HostFacts,
    InstalledService,
    KernelSettings,
    ListeningPort,
    Memory,
    Mount,
    Privileges,
    TimeSync,
)
from basewright.preflight import Outcome, evaluate
from basewright.preflight.shared import SHARED_RULES
from basewright.profiles import load_profile
from basewright.profiles.model import Conflict, Minimums, PathSpec, Preferences, Profile
from basewright.request import resolve_request

ROOT = Path(__file__).resolve().parents[2]
PROFILE = load_profile(ROOT / "test" / "fixtures" / "profiles" / "exampledb")
TYPICAL = load_facts(ROOT / "test" / "fixtures" / "hosts" / "typical.json")

#: Pinned, because one rule reads the calendar. Comfortably inside the support of the
#: fixture profile's default version, which reaches end of life in 2029.
TODAY = date(2026, 9, 4)


def outcomes(
    facts: HostFacts | None = None,
    profile: Profile | None = None,
    **request: object,
) -> dict[str, Outcome]:
    """Every rule's outcome, keyed by identifier."""
    host = facts or TYPICAL
    engine = profile or PROFILE
    resolved = resolve_request(
        engine,
        host=str(request.pop("host", host.host)),
        environment="production",
        **request,  # type: ignore[arg-type]
    )
    result = evaluate(host, engine, resolved, today=TODAY)
    return {entry.identifier: entry.outcome for entry in result.results}


def observed(rule: str, facts: HostFacts | None = None, profile: Profile | None = None) -> str:
    host = facts or TYPICAL
    engine = profile or PROFILE
    resolved = resolve_request(engine, host=host.host, environment="production")
    result = evaluate(host, engine, resolved, today=TODAY)
    return next(entry.observed for entry in result.results if entry.identifier == rule)


def mount(path: str, **overrides: object) -> Mount:
    defaults: dict[str, object] = {
        "filesystem": "ext4",
        "total_bytes": 1099511627776,
        "free_bytes": 549755813888,
        "rotational": False,
    }
    defaults.update(overrides)
    return Mount(path=path, **defaults)  # type: ignore[arg-type]


def test_every_rule_in_the_brief_is_implemented() -> None:
    """Twenty shared rules, and the identifiers are the ones the brief names."""
    assert {rule.identifier for rule in SHARED_RULES} == {
        "arch.supported",
        "cpu.min_cores",
        "disk.filesystem",
        "disk.free_space",
        "disk.paths_writable",
        "disk.separate_mounts",
        "engine.not_installed",
        "firewall.state",
        "host.privilege",
        "host.reachable",
        "locale.present",
        "mem.min_total",
        "os.supported",
        "os.swappiness",
        "os.thp",
        "port.free",
        "repo.reachable",
        "time.sync",
        "version.eol",
        "version.not_default",
    }


def test_every_rule_is_evaluated_against_every_host() -> None:
    """Twenty shared rules plus the three the fixture profile contributes."""
    assert len(outcomes()) == len(SHARED_RULES) + len(PROFILE.gates)


# ------------------------------------------------------------------- reaching the host


def test_reachable_passes_when_the_facts_describe_the_host_requested() -> None:
    assert outcomes()["host.reachable"] is Outcome.PASS


def test_reachable_blocks_when_the_facts_describe_another_machine() -> None:
    assert outcomes(host="db-somewhere-else.invalid")["host.reachable"] is Outcome.BLOCK


def test_reachable_names_both_hosts() -> None:
    facts = replace(TYPICAL, host="db-typical.invalid")
    profile = PROFILE
    resolved = resolve_request(profile, host="db-other.invalid", environment="production")
    result = evaluate(facts, profile, resolved, today=TODAY)
    entry = next(e for e in result.results if e.identifier == "host.reachable")
    assert "db-typical.invalid" in entry.observed
    assert "db-other.invalid" in entry.observed


def test_privilege_passes_when_the_account_can_escalate() -> None:
    assert outcomes()["host.privilege"] is Outcome.PASS


def test_privilege_blocks_when_it_cannot() -> None:
    facts = replace(TYPICAL, privileges=Privileges(user="reader", can_escalate=False))
    assert outcomes(facts)["host.privilege"] is Outcome.BLOCK


# ------------------------------------------------------------------------- the ground


def test_os_supported_passes_on_a_distribution_in_the_matrix() -> None:
    assert outcomes()["os.supported"] is Outcome.PASS


def test_os_supported_blocks_on_a_version_that_is_not() -> None:
    facts = replace(TYPICAL, os=replace(TYPICAL.os, version="18.04"))
    assert outcomes(facts)["os.supported"] is Outcome.BLOCK


def test_os_supported_blocks_on_a_distribution_that_is_not() -> None:
    facts = replace(TYPICAL, os=replace(TYPICAL.os, distro="arch"))
    assert outcomes(facts)["os.supported"] is Outcome.BLOCK


def test_os_supported_lists_what_is_supported() -> None:
    facts = replace(TYPICAL, os=replace(TYPICAL.os, version="18.04"))
    assert "ubuntu 24.04" in observed("os.supported", facts)


def test_arch_supported_passes_on_an_architecture_in_the_matrix() -> None:
    assert outcomes()["arch.supported"] is Outcome.PASS


def test_arch_supported_blocks_on_one_that_is_not() -> None:
    assert outcomes(replace(TYPICAL, arch="ppc64le"))["arch.supported"] is Outcome.BLOCK


def test_min_cores_passes_with_enough() -> None:
    assert outcomes()["cpu.min_cores"] is Outcome.PASS


def test_min_cores_blocks_with_too_few() -> None:
    facts = replace(TYPICAL, cpu=Cpu(cores=1))
    assert outcomes(facts)["cpu.min_cores"] is Outcome.BLOCK


def test_min_cores_skips_when_the_profile_states_no_floor() -> None:
    """It does not invent one. A number nobody agreed to would refuse hosts in its name."""
    profile = replace(PROFILE, minimums=Minimums(memory=PROFILE.minimums.memory))
    assert outcomes(profile=profile)["cpu.min_cores"] is Outcome.SKIP


def test_min_memory_passes_with_enough() -> None:
    assert outcomes()["mem.min_total"] is Outcome.PASS


def test_min_memory_blocks_with_too_little() -> None:
    facts = replace(TYPICAL, memory=Memory(total_bytes=1073741824))
    assert outcomes(facts)["mem.min_total"] is Outcome.BLOCK


def test_min_memory_skips_when_the_profile_states_no_floor() -> None:
    profile = replace(PROFILE, minimums=Minimums(cores=PROFILE.minimums.cores))
    assert outcomes(profile=profile)["mem.min_total"] is Outcome.SKIP


def test_min_memory_quotes_the_requirement_as_the_profile_wrote_it() -> None:
    """Not re-rendered. '2GB' in the file has to read as '2GB' in the refusal."""
    facts = replace(TYPICAL, memory=Memory(total_bytes=1073741824))
    assert "2GB" in observed("mem.min_total", facts)


# ---------------------------------------------------------------------------- storage


def test_paths_writable_passes_when_every_path_is_on_a_writable_mount() -> None:
    assert outcomes()["disk.paths_writable"] is Outcome.PASS


def test_paths_writable_blocks_on_a_read_only_mount() -> None:
    mounts = (mount("/", options=("ro",)),)
    assert outcomes(replace(TYPICAL, mounts=mounts))["disk.paths_writable"] is Outcome.BLOCK


def test_paths_writable_blocks_when_no_mount_carries_a_path() -> None:
    """A path on no reported filesystem is not on this machine."""
    mounts = (mount("/var/lib"),)
    assert outcomes(replace(TYPICAL, mounts=mounts))["disk.paths_writable"] is Outcome.BLOCK


def test_free_space_passes_when_every_path_has_what_it_needs() -> None:
    assert outcomes()["disk.free_space"] is Outcome.PASS


def test_free_space_blocks_when_one_path_is_short() -> None:
    mounts = tuple(
        replace(entry, free_bytes=1073741824) if entry.path == "/backup" else entry
        for entry in TYPICAL.mounts
    )
    assert outcomes(replace(TYPICAL, mounts=mounts))["disk.free_space"] is Outcome.BLOCK


def test_free_space_names_the_path_the_mount_and_both_numbers() -> None:
    mounts = tuple(
        replace(entry, free_bytes=1073741824) if entry.path == "/backup" else entry
        for entry in TYPICAL.mounts
    )
    detail = observed("disk.free_space", replace(TYPICAL, mounts=mounts))
    assert "backup" in detail
    assert "/backup" in detail
    assert "50GB" in detail
    assert "1.0 GiB" in detail


def test_free_space_skips_when_no_path_states_a_minimum() -> None:
    paths = {purpose: replace(spec, min_free=None) for purpose, spec in PROFILE.paths.items()}
    assert outcomes(profile=replace(PROFILE, paths=paths))["disk.free_space"] is Outcome.SKIP


def test_separate_mounts_warns_when_two_paths_share_one() -> None:
    """The fixture host keeps data and the journal on one filesystem."""
    assert outcomes()["disk.separate_mounts"] is Outcome.WARN


def test_separate_mounts_passes_when_they_do_not() -> None:
    mounts = (*TYPICAL.mounts, mount("/var/lib/basewright/exampledb/main/journal"))
    assert outcomes(replace(TYPICAL, mounts=mounts))["disk.separate_mounts"] is Outcome.PASS


def test_separate_mounts_skips_when_no_path_asks_to_be_kept_apart() -> None:
    paths = {
        purpose: replace(spec, prefer_separate_from=()) for purpose, spec in PROFILE.paths.items()
    }
    profile = replace(PROFILE, paths=paths)
    assert outcomes(profile=profile)["disk.separate_mounts"] is Outcome.SKIP


def test_filesystem_passes_on_a_filesystem_the_profile_prefers() -> None:
    assert outcomes()["disk.filesystem"] is Outcome.PASS


def test_filesystem_warns_on_one_it_does_not() -> None:
    mounts = tuple(replace(entry, filesystem="btrfs") for entry in TYPICAL.mounts)
    assert outcomes(replace(TYPICAL, mounts=mounts))["disk.filesystem"] is Outcome.WARN


def test_filesystem_skips_when_the_profile_prefers_none() -> None:
    profile = replace(PROFILE, preferences=replace(PROFILE.preferences, filesystems=()))
    assert outcomes(profile=profile)["disk.filesystem"] is Outcome.SKIP


# ------------------------------------------------------------------------ the machine


def test_port_free_passes_when_nothing_is_listening() -> None:
    assert outcomes()["port.free"] is Outcome.PASS


def test_port_free_blocks_when_something_is() -> None:
    listening = (
        *TYPICAL.listening_ports,
        ListeningPort(port=6432, address="0.0.0.0", protocol="tcp", process="something"),
    )
    facts = replace(TYPICAL, listening_ports=listening)
    assert outcomes(facts)["port.free"] is Outcome.BLOCK


def test_port_free_reads_the_requested_port_not_the_default() -> None:
    listening = (
        *TYPICAL.listening_ports,
        ListeningPort(port=6432, address="0.0.0.0", protocol="tcp", process="something"),
    )
    facts = replace(TYPICAL, listening_ports=listening)
    assert outcomes(facts, port=6433)["port.free"] is Outcome.PASS


def test_not_installed_passes_on_a_host_with_nothing_conflicting() -> None:
    assert outcomes()["engine.not_installed"] is Outcome.PASS


def test_not_installed_blocks_when_a_declared_conflict_is_present() -> None:
    services = (InstalledService(name="exampledb-3", state="running"),)
    facts = replace(TYPICAL, services=services)
    assert outcomes(facts)["engine.not_installed"] is Outcome.BLOCK


def test_not_installed_ignores_a_service_the_profile_says_nothing_about() -> None:
    """The core recognises nothing on its own; a name it was not given is not a conflict."""
    services = (InstalledService(name="nginx", state="running"),)
    facts = replace(TYPICAL, services=services)
    assert outcomes(facts)["engine.not_installed"] is Outcome.PASS


def test_not_installed_matches_exactly_when_the_conflict_says_so() -> None:
    conflicts = (Conflict(service="exampledb", description="an instance", match="exact"),)
    profile = replace(PROFILE, conflicts=conflicts)
    services = (InstalledService(name="exampledb-3", state="running"),)
    facts = replace(TYPICAL, services=services)
    assert outcomes(facts, profile=profile)["engine.not_installed"] is Outcome.PASS


def test_not_installed_skips_when_the_profile_declares_no_conflicts() -> None:
    assert outcomes(profile=replace(PROFILE, conflicts=()))["engine.not_installed"] is Outcome.SKIP


def test_repo_reachable_passes_when_the_host_reached_it() -> None:
    url = "https://packages.example.invalid/apt"
    facts = replace(TYPICAL, reachable_repositories=(url,))
    assert outcomes(facts)["repo.reachable"] is Outcome.PASS


def test_repo_reachable_blocks_when_the_host_was_asked_and_reached_nothing() -> None:
    """An empty list is an answer. It is not the same as never having asked."""
    facts = replace(TYPICAL, reachable_repositories=())
    assert outcomes(facts)["repo.reachable"] is Outcome.BLOCK


def test_repo_reachable_skips_when_nobody_asked() -> None:
    assert outcomes()["repo.reachable"] is Outcome.SKIP


def test_repo_reachable_skips_when_the_profile_declares_no_repository() -> None:
    packages = {
        family: replace(entry, repository=None) for family, entry in PROFILE.packages.items()
    }
    facts = replace(TYPICAL, reachable_repositories=())
    profile = replace(PROFILE, packages=packages)
    assert outcomes(facts, profile=profile)["repo.reachable"] is Outcome.SKIP


def test_locale_present_passes_when_the_host_has_it() -> None:
    assert outcomes()["locale.present"] is Outcome.PASS


def test_locale_present_blocks_when_it_does_not() -> None:
    facts = replace(TYPICAL, locales=("C.UTF-8",))
    assert outcomes(facts)["locale.present"] is Outcome.BLOCK


def test_locale_present_skips_when_the_profile_names_none() -> None:
    assert outcomes(profile=replace(PROFILE, default_locale=None))["locale.present"] is Outcome.SKIP


def test_thp_warns_when_the_setting_is_not_one_the_profile_prefers() -> None:
    assert outcomes()["os.thp"] is Outcome.WARN


def test_thp_passes_when_it_is() -> None:
    facts = replace(TYPICAL, kernel=replace(TYPICAL.kernel, transparent_hugepages="madvise"))
    assert outcomes(facts)["os.thp"] is Outcome.PASS


def test_thp_skips_when_the_host_did_not_report_it() -> None:
    assert outcomes(replace(TYPICAL, kernel=None))["os.thp"] is Outcome.SKIP


def test_thp_skips_when_the_profile_prefers_nothing() -> None:
    profile = replace(PROFILE, preferences=replace(PROFILE.preferences, transparent_hugepages=()))
    assert outcomes(profile=profile)["os.thp"] is Outcome.SKIP


def test_swappiness_warns_above_what_the_profile_prefers() -> None:
    assert outcomes()["os.swappiness"] is Outcome.WARN


def test_swappiness_passes_at_or_below_it() -> None:
    facts = replace(TYPICAL, kernel=replace(TYPICAL.kernel, swappiness=10))
    assert outcomes(facts)["os.swappiness"] is Outcome.PASS


def test_swappiness_skips_when_the_host_did_not_report_it() -> None:
    facts = replace(TYPICAL, kernel=KernelSettings(transparent_hugepages="madvise"))
    assert outcomes(facts)["os.swappiness"] is Outcome.SKIP


def test_swappiness_skips_when_the_profile_prefers_nothing() -> None:
    profile = replace(PROFILE, preferences=replace(PROFILE.preferences, max_swappiness=None))
    assert outcomes(profile=profile)["os.swappiness"] is Outcome.SKIP


def test_time_sync_passes_when_the_clock_is_kept() -> None:
    assert outcomes()["time.sync"] is Outcome.PASS


def test_time_sync_warns_when_it_is_not_synchronized() -> None:
    facts = replace(TYPICAL, time_sync=TimeSync(service="chrony", synchronized=False))
    assert outcomes(facts)["time.sync"] is Outcome.WARN


def test_time_sync_skips_when_the_host_reported_no_service() -> None:
    assert outcomes(replace(TYPICAL, time_sync=None))["time.sync"] is Outcome.SKIP


def test_firewall_warns_when_it_is_active_and_does_not_admit_the_port() -> None:
    assert outcomes()["firewall.state"] is Outcome.WARN


def test_firewall_passes_when_it_admits_the_port() -> None:
    facts = replace(TYPICAL, firewall=Firewall(service="ufw", active=True, open_ports=(22, 6432)))
    assert outcomes(facts)["firewall.state"] is Outcome.PASS


def test_firewall_passes_when_it_is_inactive() -> None:
    facts = replace(TYPICAL, firewall=Firewall(service="ufw", active=False))
    assert outcomes(facts)["firewall.state"] is Outcome.PASS


def test_firewall_skips_when_the_host_reported_none() -> None:
    assert outcomes(replace(TYPICAL, firewall=None))["firewall.state"] is Outcome.SKIP


# ------------------------------------------------------------------------- the version


def test_eol_passes_when_support_runs_well_past_the_horizon() -> None:
    assert outcomes()["version.eol"] is Outcome.PASS


def test_eol_warns_within_twelve_months() -> None:
    versions = tuple(replace(entry, eol=date(2027, 1, 1)) for entry in PROFILE.versions)
    assert outcomes(profile=replace(PROFILE, versions=versions))["version.eol"] is Outcome.WARN


def test_eol_warns_after_it_has_passed_and_says_so() -> None:
    versions = tuple(replace(entry, eol=date(2025, 1, 1)) for entry in PROFILE.versions)
    profile = replace(PROFILE, versions=versions)
    assert outcomes(profile=profile)["version.eol"] is Outcome.WARN
    assert "has passed" in observed("version.eol", profile=profile)


def test_not_default_passes_on_the_profile_default() -> None:
    assert outcomes()["version.not_default"] is Outcome.PASS


def test_not_default_warns_on_a_version_a_person_chose() -> None:
    assert outcomes(version="2")["version.not_default"] is Outcome.WARN


# ---------------------------------------------------------------- severity resolution


@pytest.mark.parametrize(
    "rule",
    [rule for rule in SHARED_RULES if rule.severity == "block"],
    ids=lambda rule: rule.identifier,
)
def test_a_blocking_rule_never_reports_a_warning(rule: object) -> None:
    """Severity decides what an unmet rule costs, and nothing at run time changes it."""
    identifier = rule.identifier  # type: ignore[attr-defined]
    assert outcomes()[identifier] in {Outcome.PASS, Outcome.BLOCK, Outcome.SKIP}


@pytest.mark.parametrize(
    "rule",
    [rule for rule in SHARED_RULES if rule.severity == "warn"],
    ids=lambda rule: rule.identifier,
)
def test_a_warning_rule_never_blocks(rule: object) -> None:
    identifier = rule.identifier  # type: ignore[attr-defined]
    assert outcomes()[identifier] in {Outcome.PASS, Outcome.WARN, Outcome.SKIP}


def test_every_unmet_rule_carries_a_remedy() -> None:
    """A refusal nobody can act on is a refusal that gets worked around."""
    resolved = resolve_request(PROFILE, host=TYPICAL.host, environment="production")
    result = evaluate(TYPICAL, PROFILE, resolved, today=TODAY)
    for entry in result.results:
        if entry.outcome is not Outcome.PASS:
            assert entry.remediation, f"{entry.identifier} reported {entry.outcome} with no remedy"


def test_every_result_carries_what_was_observed() -> None:
    resolved = resolve_request(PROFILE, host=TYPICAL.host, environment="production")
    result = evaluate(TYPICAL, PROFILE, resolved, today=TODAY)
    for entry in result.results:
        assert entry.observed, f"{entry.identifier} reported nothing it saw"


def test_a_path_spec_is_what_the_layout_declared() -> None:
    """The fixture layout is the one these tests vary; a change to it changes them."""
    journal = PROFILE.paths["journal"]
    assert isinstance(journal, PathSpec)
    assert journal.prefer_separate_from == ("data",)


def test_preferences_are_the_profiles_and_not_the_cores() -> None:
    assert PROFILE.preferences == Preferences(
        filesystems=("ext4", "xfs"),
        transparent_hugepages=("madvise", "never"),
        max_swappiness=10,
    )
