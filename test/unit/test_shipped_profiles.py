"""The profiles this repository ships, held to what a shipped profile has to be.

`profiles/` is the extension point, and until now it was empty: everything the schema and
the loader could be shown to do was shown against a fictional engine under `test/`. That
was honest and it proved something narrower than it looked. A fixture is written by whoever
is writing the loader, on the same afternoon, and it asks the questions they already had in
mind.

These checks are what a profile has to survive to be one somebody provisions with. Two of
them are about honesty rather than validity: every threshold that becomes a block is a
number somebody has to defend in a review, and a value nobody has confirmed is marked as an
assumption on the status page rather than presented as policy.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from basewright.facts import load_facts
from basewright.planner import build_plan
from basewright.preflight import evaluate
from basewright.profiles import known_engines, load_profile, profiles_directory
from basewright.profiles.model import Profile
from basewright.request import resolve_request

ROOT = Path(__file__).resolve().parents[2]
HOSTS = ROOT / "test" / "fixtures" / "hosts"
STATUS = ROOT / "docs" / "dev" / "STATUS.md"

SHIPPED = known_engines()


def test_at_least_one_profile_ships() -> None:
    """The check below is over a list, and a check over an empty list always passes. This
    is also the line that changes the day `profiles/` stops being empty, which it has."""
    assert SHIPPED, f"no profiles found under {profiles_directory()}"


@pytest.fixture(scope="module", params=SHIPPED)
def profile(request: pytest.FixtureRequest) -> Profile:
    return load_profile(profiles_directory() / str(request.param))


def test_it_loads_and_holds_together(profile: Profile) -> None:
    """The same three passes any profile goes through. A shipped profile that only the
    schema job exercises is one whose breakage is a red CI job rather than a red test."""
    assert profile.engine
    assert profile.versions
    assert profile.paths
    assert profile.sizing


def test_every_supported_version_has_support_left(profile: Profile) -> None:
    """A profile offering a version that is already out of support is offering to build
    something nobody upstream will fix. The gate warns about it per request; this is the
    profile being wrong rather than the host."""
    for version in profile.versions:
        assert version.eol > date.today(), f"{version.version} is past its end of life"


def test_the_default_version_is_one_it_supports(profile: Profile) -> None:
    offered = {version.version for version in profile.versions}
    assert profile.default_version in offered


def test_the_default_version_is_not_one_that_only_warns(profile: Profile) -> None:
    """A default that raises a warning on every plan makes the warning worthless, which is
    the failure mode of every acknowledgement anybody has ever had to click through."""
    default = next(v for v in profile.versions if v.version == profile.default_version)
    assert default.status != "allowed_with_warning"


def test_the_port_is_one_an_unprivileged_account_can_bind(profile: Profile) -> None:
    assert profile.default_port > 1024


def test_every_sizing_rule_explains_itself(profile: Profile) -> None:
    """ADR-0009. A number with no argument behind it is the thing this tool replaces, so a
    reason that is a restatement of the rule is worse than none: it looks like one."""
    for rule in profile.sizing:
        assert len(rule.why) > 80, f"{rule.id} does not say why"
        assert rule.parameter not in rule.why, f"{rule.id} restates itself instead of arguing"


def test_every_gate_says_what_would_change_it(profile: Profile) -> None:
    """A refusal that does not name the way out is a refusal somebody works around."""
    for rule in profile.gates:
        assert len(rule.remediation) > 40, f"{rule.id} refuses without saying what to do"


def test_every_path_declares_the_room_it_needs(profile: Profile) -> None:
    """min_free is a block with no run-time override, so a path without one is a path
    nothing checks, and a path with one is a number in a pull request."""
    for purpose, spec in profile.paths.items():
        assert spec.min_free, f"{purpose} declares no free space it needs"


def test_the_status_page_says_which_values_are_still_assumptions(profile: Profile) -> None:
    """§21 of the brief allows shipping upstream defaults and requires marking them. An
    unmarked default reads as policy, and policy is what a reviewer stops questioning."""
    status = STATUS.read_text(encoding="utf-8")
    assert profile.engine in status, f"{profile.engine} ships and the status page ignores it"


@pytest.mark.parametrize("host", ["typical", "large"])
def test_a_capable_host_gets_a_plan(profile: Profile, host: str) -> None:
    """End to end, against the real profile: the gates pass, every sizing rule evaluates,
    and every path and package name resolves."""
    facts = load_facts(HOSTS / f"{host}.json")
    request = resolve_request(profile, host=facts.host, environment="production")
    gates = evaluate(facts, profile, request)

    assert not gates.blocked
    plan = build_plan(facts, profile, request, gates)
    assert plan["parameters"]
    assert len(plan["parameters"]) == len(profile.sizing)


def test_a_host_the_profile_does_not_support_is_refused(profile: Profile) -> None:
    """The fixture running an operating system outside the support matrix. A profile that
    accepted it would be one whose matrix says nothing."""
    facts = load_facts(HOSTS / "rocky.json")
    request = resolve_request(profile, host=facts.host, environment="production")

    assert evaluate(facts, profile, request).blocked


def test_an_installation_with_nowhere_to_look_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failure of a broken install rather than of a mistyped name, and it has to read
    differently: there is nothing the operator can type that would work."""
    from basewright.profiles import locate

    monkeypatch.setattr(locate, "_CANDIDATES", (Path("nowhere"), Path("nor-here")))

    assert locate.known_engines() == []
    with pytest.raises(locate.UnknownEngineError, match="no profiles directory found"):
        locate.profiles_directory()


def test_an_installation_with_no_profiles_still_names_the_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from basewright.profiles import locate

    monkeypatch.setattr(locate, "_CANDIDATES", (tmp_path,))

    with pytest.raises(locate.UnknownEngineError) as raised:
        locate.directory_for("anything")
    assert "none, which is why this is failing" in str(raised.value)
