"""Which repositories a host is asked to reach, and where that question comes from.

This is the one fact whose collection depends on knowing what is being provisioned, so it
is the one place the collecting half is told an engine's name at all. Everything about it
that could be wrong is here rather than in a playbook: which url gets probed, what it is
spelled as, and what happens when nobody said what was being provisioned.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from basewright.facts.errors import InvalidFactsError
from basewright.facts.model import HostFacts
from basewright.facts.normalize import normalize
from basewright.facts.repositories import RepositoryQuestionError, repositories, urls_for
from basewright.placeholders import PlaceholderError
from basewright.profiles import load_profile
from basewright.profiles.locate import UnknownEngineError

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "test" / "fixtures" / "profiles" / "exampledb"
HOSTS = ROOT / "test" / "fixtures" / "hosts"

PROFILE = load_profile(FIXTURE)


def document(name: str) -> dict[str, Any]:
    return json.loads((HOSTS / f"{name}.json").read_text(encoding="utf-8"))


def facts(name: str) -> HostFacts:
    return normalize(document(name))


# ------------------------------------------------------------------ which urls


def test_the_url_probed_is_the_one_the_rule_will_compare() -> None:
    """Not approximately the same url: the same string. The gate matches exactly, so a
    probe of anything else proves something about a repository nobody will install from."""
    packages = PROFILE.packages_for("debian")
    assert packages is not None and packages.repository is not None

    urls = urls_for(facts("typical"), PROFILE)

    assert urls == [packages.repository.url]


def test_a_url_is_filled_in_from_the_host_that_will_be_asked() -> None:
    """The rhel repository is keyed by the major version, which is a fact about the host
    rather than about the request, and it is the reason this cannot be a constant."""
    urls = urls_for(facts("rocky"), PROFILE)

    assert urls == ["https://packages.example.invalid/yum/el9"]


def test_a_profile_with_no_packages_for_this_family_asks_nothing() -> None:
    """Not a refusal. The rule reading the answer decides it has nothing to decide, and
    it does so before it ever looks at this fact."""
    profile = replace(PROFILE, packages={"debian": PROFILE.packages["debian"]})

    assert urls_for(facts("rocky"), profile) == []


def test_a_family_that_installs_from_what_the_host_already_has_asks_nothing() -> None:
    packages = {
        family: replace(entry, repository=None) for family, entry in PROFILE.packages.items()
    }

    assert urls_for(facts("typical"), replace(PROFILE, packages=packages)) == []


def test_the_version_asked_about_is_the_one_that_will_be_installed() -> None:
    """A url keyed by the engine version is probed for the version the request names, not
    for the profile's default -- otherwise the fact answers a question nobody asked."""
    packages = PROFILE.packages_for("debian")
    assert packages is not None and packages.repository is not None
    keyed = replace(
        packages, repository=replace(packages.repository, url="https://e/{{ version }}")
    )
    profile = replace(PROFILE, packages={**PROFILE.packages, "debian": keyed})

    assert urls_for(facts("typical"), profile) == [f"https://e/{PROFILE.default_version}"]
    assert urls_for(facts("typical"), profile, version="99") == ["https://e/99"]


def test_a_url_reaching_for_something_only_a_request_settles_is_refused() -> None:
    """Collecting happens before a request exists. A profile whose repository url is one
    string while it is probed and another while it is installed from would produce a fact
    compared against a url nobody ever tried, and the comparison would silently fail."""
    packages = PROFILE.packages_for("debian")
    assert packages is not None and packages.repository is not None
    keyed = replace(
        packages, repository=replace(packages.repository, url="https://e/{{ environment }}")
    )
    profile = replace(PROFILE, packages={**PROFILE.packages, "debian": keyed})

    with pytest.raises(PlaceholderError) as raised:
        urls_for(facts("typical"), profile)

    assert "environment" in str(raised.value)
    assert "os.codename" in str(raised.value), "the refusal should name what a url does have"


# ------------------------------------------------------------------- the bridge


def test_a_profile_directory_is_read_the_way_the_command_line_reads_one() -> None:
    assert repositories(document("typical"), profile=str(FIXTURE)) == [
        "https://packages.example.invalid/apt"
    ]


def test_an_engine_is_looked_up_under_profiles() -> None:
    urls = repositories(document("typical"), engine="postgresql")

    assert urls == ["https://apt.postgresql.org/pub/repos/apt"]


def test_an_engine_nothing_has_a_profile_for_is_refused_by_name() -> None:
    with pytest.raises(UnknownEngineError):
        repositories(document("typical"), engine="nothing-of-the-sort")


@pytest.mark.parametrize(
    "named",
    [
        pytest.param({}, id="neither"),
        pytest.param({"engine": "postgresql", "profile": str(FIXTURE)}, id="both"),
    ],
)
def test_the_question_needs_exactly_one_profile_to_come_from(named: dict[str, str]) -> None:
    """Collecting without either is allowed and is how most of this runs; what cannot be
    answered is the question put without saying whose repositories are meant."""
    with pytest.raises(RepositoryQuestionError):
        repositories(document("typical"), **named)


def test_the_document_is_read_through_the_contract_every_rule_uses() -> None:
    """A url filled in from whatever the role happened to assemble would be a url built
    from a host the core would not have accepted."""
    with pytest.raises(InvalidFactsError):
        repositories({"host": "nowhere.invalid"}, engine="postgresql")
