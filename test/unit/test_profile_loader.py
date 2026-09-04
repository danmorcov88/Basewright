"""The loader reads a profile correctly, and refuses one usefully.

The second half matters as much as the first. A profile is written by whoever knows the
engine, which is rarely whoever wrote the loader, so a rejection that does not name the
file, the place inside it and the way out is a rejection that turns the schema into a
guessing game. Every test below that asserts a refusal also asserts that the refusal can
be acted on.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from basewright.expressions import base_scope
from basewright.facts import load_facts
from basewright.layout import resolve_paths
from basewright.profiles import (
    InvalidProfileError,
    MissingProfileError,
    Problem,
    Profile,
    load_profile,
    load_profiles,
)
from basewright.profiles.loader import _RESERVED_GROUPS
from basewright.profiles.schema import PROFILE_FILES
from basewright.request import resolve_request
from basewright.scope import build_scope

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "test" / "fixtures" / "profiles"


@pytest.fixture
def profile() -> Profile:
    return load_profile(FIXTURES / "exampledb")


def refuse(name: str) -> list[Problem]:
    """Load a fixture that is meant to fail, and return why it did."""
    with pytest.raises(InvalidProfileError) as raised:
        load_profile(FIXTURES / name)
    return raised.value.problems


def located(problems: list[Problem]) -> list[str]:
    return [f"{problem.file}:{problem.location}" for problem in problems]


# ------------------------------------------------------------------------------- reading


def test_identity_is_read(profile: Profile) -> None:
    assert profile.engine == "exampledb"
    assert profile.display_name == "ExampleDB"
    assert profile.profile_version == "1.0.0"
    assert profile.os_families == ("debian", "rhel")
    assert profile.default_port == 6432
    assert profile.default_instance == "main"


def test_the_support_matrix_becomes_dates_and_not_strings(profile: Profile) -> None:
    """A date left as text is a comparison waiting to be written wrongly."""
    latest = profile.version("3")
    assert latest is not None
    assert latest.eol == date(2029, 5, 1)
    assert latest.status == "supported"
    assert profile.default_version == "3"


def test_a_version_without_a_status_is_supported(profile: Profile) -> None:
    older = profile.version("2")
    assert older is not None
    assert older.status == "allowed_with_warning"


def test_a_version_knows_the_ground_it_runs_on(profile: Profile) -> None:
    latest = profile.version("3")
    assert latest is not None
    assert latest.supports(distro="ubuntu", version="24.04", arch="x86_64")
    assert not latest.supports(distro="ubuntu", version="20.04", arch="x86_64")
    assert not latest.supports(distro="ubuntu", version="24.04", arch="ppc64le")


def test_an_unlisted_version_is_not_invented(profile: Profile) -> None:
    assert profile.version("99") is None


def test_gates_carry_their_severity_and_their_way_out(profile: Profile) -> None:
    blocking = [gate for gate in profile.gates if gate.blocking]
    warning = [gate for gate in profile.gates if not gate.blocking]

    assert len(blocking) == 1
    assert len(warning) == 2
    assert all(gate.remediation for gate in profile.gates)
    assert {gate.severity for gate in profile.gates} == {"block", "warn"}


def test_sizing_rules_carry_their_reasoning(profile: Profile) -> None:
    """The reasoning is what makes the plan reviewable; a rule without it is a number."""
    assert all(rule.why for rule in profile.sizing)
    cache = next(rule for rule in profile.sizing if rule.parameter == "cache_size")
    assert cache.identifier == "exampledb.cache_size"
    assert cache.unit == "bytes"
    assert cache.minimum == "128MiB"
    assert cache.maximum == "8GiB"


def test_a_sizing_rule_without_bounds_reports_none(profile: Profile) -> None:
    interval = next(rule for rule in profile.sizing if rule.parameter == "checkpoint_interval")
    assert interval.minimum is None
    assert interval.maximum is None
    assert interval.warn_above is None


def test_layout_and_the_service_account_are_read(profile: Profile) -> None:
    data = profile.path("data")
    assert data is not None
    assert data.mode == "0700"
    assert data.min_free == "20GB"
    assert profile.path("nowhere") is None
    assert profile.service_account.create_if_missing is True
    assert profile.service_account.shell == "/usr/sbin/nologin"


def test_packages_are_read_per_family(profile: Profile) -> None:
    debian = profile.packages_for("debian")
    assert debian is not None
    assert debian.repository is not None
    assert debian.repository.components == ("main",)
    assert debian.repository.gpg_check is True

    rhel = profile.packages_for("rhel")
    assert rhel is not None
    assert rhel.repository is not None
    assert rhel.repository.components == ()

    assert profile.packages_for("windows") is None


def test_verify_checks_are_read(profile: Profile) -> None:
    kinds = {check.kind for check in profile.checks}
    assert "service" in kinds
    assert all(check.remediation for check in profile.checks)


def test_the_templates_directory_is_where_the_profile_says(profile: Profile) -> None:
    assert profile.templates == FIXTURES / "exampledb" / "templates"
    assert profile.templates.is_dir()


def test_a_directory_of_profiles_loads(tmp_path: Path) -> None:
    assert load_profiles(tmp_path) == []

    shutil.copytree(FIXTURES / "exampledb", tmp_path / "one")
    shutil.copytree(FIXTURES / "exampledb", tmp_path / "two")

    assert [profile.root.name for profile in load_profiles(tmp_path)] == ["one", "two"]


# ---------------------------------------------------------------------------- refusing


def test_a_missing_directory_is_not_an_empty_profile(tmp_path: Path) -> None:
    with pytest.raises(MissingProfileError):
        load_profile(tmp_path / "not-here")


def test_a_missing_file_is_reported_as_a_missing_file(tmp_path: Path) -> None:
    """Six files out of seven is not a profile with a default for the seventh."""
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    for name in PROFILE_FILES[:-1]:
        (incomplete / name).write_text(
            (FIXTURES / "exampledb" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )

    with pytest.raises(InvalidProfileError) as raised:
        load_profile(incomplete)

    assert located(raised.value.problems) == ["verify.yml:"]
    assert raised.value.problems[0].message == "is missing"


def test_a_file_that_is_not_yaml_says_so(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    for name in PROFILE_FILES:
        (broken / name).write_text(
            (FIXTURES / "exampledb" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (broken / "sizing.yml").write_text("---\nrules: [\n", encoding="utf-8")

    problems = [p for p in _problems(broken) if p.file == "sizing.yml"]

    assert problems[0].message == "is not valid YAML"
    assert problems[0].hint


def test_a_file_that_is_not_a_mapping_says_so(tmp_path: Path) -> None:
    broken = tmp_path / "notamapping"
    broken.mkdir()
    for name in PROFILE_FILES:
        (broken / name).write_text(
            (FIXTURES / "exampledb" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (broken / "verify.yml").write_text("---\n- a list\n", encoding="utf-8")

    problems = _problems(broken)

    assert problems[0].message.startswith("is list, not a mapping")


def _problems(directory: Path) -> list[Problem]:
    with pytest.raises(InvalidProfileError) as raised:
        load_profile(directory)
    return raised.value.problems


# ------------------------------------------------------- refusing: schema violations


def test_a_malformed_profile_reports_every_defect_at_once() -> None:
    """One error per run is how a profile takes an afternoon instead of ten minutes."""
    problems = refuse("malformed")

    assert located(problems) == [
        "apply.yml:configuration[0].template",
        "layout.yml:paths.log",
        "requirements.yml:rules[0].severity",
        "requirements.yml:rules[1].override",
        "sizing.yml:rules[0].why",
        "support-matrix.yml:versions[0].eol",
    ]


def test_a_third_severity_is_refused_with_the_two_that_exist() -> None:
    """There is no override flag anywhere; the enumeration is the whole policy."""
    problem = _only("malformed", "requirements.yml:rules[0].severity")

    assert problem.message == "'fatal' is not one of: block, warn"
    assert "two severities" in problem.hint


def test_an_unknown_key_names_the_keys_that_do_exist() -> None:
    problem = _only("malformed", "requirements.yml:rules[1].override")

    assert problem.message == "is not a key this schema defines"
    assert "applies_to, expr, id, remediation, severity, title" in problem.hint


def test_a_sizing_rule_without_reasoning_is_refused() -> None:
    problem = _only("malformed", "sizing.yml:rules[0].why")

    assert problem.message == "is required but missing"
    assert "plan" in problem.hint


def test_a_date_that_is_not_a_date_shows_the_shape_expected() -> None:
    problem = _only("malformed", "support-matrix.yml:versions[0].eol")

    assert problem.message.startswith("'1 May 2029' does not match ")


# ---------------------------------------------------- refusing: disagreements between files


def test_files_that_disagree_are_reported_even_though_each_one_is_valid() -> None:
    problems = refuse("inconsistent")

    assert located(problems) == [
        "apply.yml:configuration[1].carries_parameters",
        "apply.yml:configuration[1].template",
        "layout.yml:engine",
        "packages.yml:families.rhel",
        "sizing.yml:rules[1].id",
        "sizing.yml:rules[2].parameter",
        "support-matrix.yml:default_version",
        "support-matrix.yml:versions[0].supported_os[1].family",
    ]


def test_a_file_belonging_to_another_profile_is_caught() -> None:
    problem = _only("inconsistent", "layout.yml:engine")

    assert problem.message == "is 'other', but profile.yml declares 'inconsistent'"


def test_a_default_version_nobody_supports_is_caught() -> None:
    problem = _only("inconsistent", "support-matrix.yml:default_version")

    assert problem.message == "is '4', which is not one of the versions listed"
    assert "Listed versions are: 3." in problem.hint


def test_a_family_the_profile_does_not_declare_is_caught() -> None:
    problem = _only("inconsistent", "support-matrix.yml:versions[0].supported_os[1].family")

    assert problem.message == "is 'suse', which profile.yml does not declare"
    assert "debian, rhel" in problem.hint


def test_a_family_that_cannot_be_installed_on_is_caught() -> None:
    """Claiming ground the profile cannot install on refuses at the latest possible moment."""
    problem = _only("inconsistent", "packages.yml:families.rhel")

    assert problem.message == "is declared in profile.yml but has no packages here"


def test_an_identifier_used_twice_is_caught() -> None:
    problem = _only("inconsistent", "sizing.yml:rules[1].id")

    assert problem.message == "'inconsistent.cache_size' is already used by rules[0]"


def _only(fixture: str, location: str) -> Problem:
    problems = [p for p in refuse(fixture) if f"{p.file}:{p.location}" == location]
    assert len(problems) == 1, f"expected exactly one problem at {location}"
    return problems[0]


# ------------------------------------------------------------------------- the report


def test_the_report_names_the_file_the_place_and_the_way_out() -> None:
    with pytest.raises(InvalidProfileError) as raised:
        load_profile(FIXTURES / "malformed")

    report = raised.value.report()

    assert "6 problems" in report
    assert "requirements.yml" in report
    assert "rules[0].severity" in report
    assert "->" in report


def test_the_report_carries_no_absolute_path() -> None:
    """Reports are compared byte for byte in CI and read on three operating systems."""
    with pytest.raises(InvalidProfileError) as raised:
        load_profile(FIXTURES / "malformed")

    report = raised.value.report()

    assert str(ROOT) not in report
    assert ROOT.as_posix() not in report
    assert "\\" not in report


def test_the_report_wraps_to_a_width_a_terminal_can_show() -> None:
    with pytest.raises(InvalidProfileError) as raised:
        load_profile(FIXTURES / "inconsistent")

    longest = max(len(line) for line in raised.value.report().splitlines())

    assert longest <= 88


# ------------------------------------------------------ paths kept apart from each other


def _with_layout(tmp_path: Path, replacement: str, into: str) -> Path:
    """A copy of the fixture profile with one line of its layout changed."""
    copied = tmp_path / "edited"
    shutil.copytree(FIXTURES / "exampledb", copied)
    layout = copied / "layout.yml"
    layout.write_text(
        layout.read_text(encoding="utf-8").replace(replacement, into, 1), encoding="utf-8"
    )
    return copied


def test_a_path_may_not_prefer_to_be_separate_from_one_that_does_not_exist(
    tmp_path: Path,
) -> None:
    """A purpose that is not there reads as a rule about storage and is no rule at all."""
    edited = _with_layout(tmp_path, "prefer_separate_from: [data]", "prefer_separate_from: [dta]")
    with pytest.raises(InvalidProfileError) as raised:
        load_profile(edited)
    problems = raised.value.problems
    assert "layout.yml:paths.journal.prefer_separate_from[0]" in located(problems)
    assert any("which this layout does not define" in problem.message for problem in problems)
    assert all(problem.hint for problem in problems)


def test_a_path_may_not_prefer_to_be_separate_from_itself(tmp_path: Path) -> None:
    edited = _with_layout(
        tmp_path, "prefer_separate_from: [data]", "prefer_separate_from: [journal]"
    )
    with pytest.raises(InvalidProfileError) as raised:
        load_profile(edited)
    assert any("which is the path itself" in problem.message for problem in raised.value.problems)


def test_the_thresholds_a_shared_rule_reads_are_the_profiles(profile: Profile) -> None:
    """Every number a shared gate compares against comes from here, not from the core."""
    assert profile.minimums.cores == 2
    assert profile.minimums.memory == "2GB"
    assert profile.minimums.memory_bytes == 2_000_000_000
    assert profile.preferences.max_swappiness == 10
    assert profile.default_locale == "en_US.UTF-8"


def test_a_profile_may_state_none_of_them(tmp_path: Path) -> None:
    """They are all optional, and a rule with nothing to compare against skips."""
    copied = tmp_path / "bare"
    shutil.copytree(FIXTURES / "exampledb", copied)
    requirements = copied / "requirements.yml"
    requirements.write_text("---\nengine: exampledb\nrules: []\n", encoding="utf-8")

    bare = load_profile(copied)
    assert bare.minimums.cores is None
    assert bare.minimums.memory is None
    assert bare.preferences.filesystems == ()
    assert bare.conflicts == ()
    assert bare.gates == ()


def test_a_conflict_matches_exactly_or_by_prefix(profile: Profile) -> None:
    """The core recognises nothing on its own; what conflicts is what the profile said."""
    assert profile.conflicting("exampledb") is not None
    assert profile.conflicting("exampledb-3") is not None
    assert profile.conflicting("exampledb@3-main") is not None
    assert profile.conflicting("nginx") is None
    assert profile.conflicting("notexampledb") is None


# ------------------------------------------------------------------- what apply will do


def test_a_profile_declares_the_files_apply_writes(profile: Profile) -> None:
    """Nothing else in a profile says what apply will do to the machine."""
    identifiers = [entry.identifier for entry in profile.configuration]

    assert identifiers == ["exampledb.server_config", "exampledb.access_config"]
    assert profile.configuration[0].carries_parameters
    assert not profile.configuration[1].carries_parameters


def test_a_host_setting_carries_the_expression_that_reads_it_now(profile: Profile) -> None:
    """An expression, not a name the core maps: a table of settings in the core is a table
    that has to grow every time a profile wants one nobody thought of."""
    swappiness = profile.tunables[0]

    assert swappiness.name == "vm.swappiness"
    assert swappiness.observed == "host.kernel.swappiness"
    assert len(swappiness.why) > 10


def test_a_secret_has_a_name_and_a_place_and_no_third_field(profile: Profile) -> None:
    """The strongest form of never logging a secret is having nowhere to put one."""
    secret = profile.secrets[0]

    assert "{{ instance }}" in secret.location
    assert not hasattr(secret, "value")


def test_the_reserved_names_are_the_ones_a_scope_actually_has(profile: Profile) -> None:
    """The loader refuses a parameter that shadows the vocabulary, from a list written
    down beside it. If the two ever drift, the refusal guards the wrong names."""
    facts = load_facts(ROOT / "test" / "fixtures" / "hosts" / "typical.json")
    request = resolve_request(profile, host=facts.host, environment="production")
    scope = build_scope(facts, profile, request, resolve_paths(profile, request))

    assert set(_RESERVED_GROUPS) == set(scope) - set(base_scope())
