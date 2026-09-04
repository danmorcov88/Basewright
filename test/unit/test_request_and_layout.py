"""Resolving a request against a profile, and the paths that follow from it.

Two small pieces that everything after them depends on. A version the matrix does not
list is refused here rather than by a gate, because the fault is in the request rather
than in the machine, and a placeholder nobody defined is an error rather than a directory
with braces in its name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from basewright.layout import LayoutError, resolve_path, resolve_paths
from basewright.placeholders import PlaceholderError
from basewright.profiles import load_profile
from basewright.request import Request, RequestError, resolve_request, supported_version

ROOT = Path(__file__).resolve().parents[2]
PROFILE = load_profile(ROOT / "test" / "fixtures" / "profiles" / "exampledb")


def request(**overrides: object) -> Request:
    arguments: dict[str, object] = {"host": "db.invalid", "environment": "production"}
    arguments.update(overrides)
    return resolve_request(PROFILE, **arguments)  # type: ignore[arg-type]


# ------------------------------------------------------------------------- the request


def test_defaults_come_from_the_profile() -> None:
    resolved = request()
    assert resolved.engine == "exampledb"
    assert resolved.version == "3"
    assert resolved.instance == "main"
    assert resolved.port == 6432
    assert resolved.locale == "en_US.UTF-8"


def test_what_was_supplied_wins() -> None:
    resolved = request(version="2", instance="reporting", port=6433)
    assert resolved.version == "2"
    assert resolved.instance == "reporting"
    assert resolved.port == 6433


def test_the_source_of_the_version_is_recorded() -> None:
    """A version a person chose and a version nobody chose are not the same decision."""
    assert request().version_source == "profile_default"
    assert request().chosen_version is False
    assert request(version="2").version_source == "requested"
    assert request(version="2").chosen_version is True


def test_a_version_the_matrix_does_not_list_is_refused() -> None:
    with pytest.raises(RequestError, match="not a version this profile supports"):
        request(version="9")


def test_the_refusal_lists_what_is_supported() -> None:
    with pytest.raises(RequestError, match="It lists: 3, 2"):
        request(version="9")


def test_the_matrix_entry_is_reachable_afterwards() -> None:
    assert supported_version(PROFILE, request()).version == "3"


def test_the_request_renders_as_an_artifact_carries_it() -> None:
    document = request().document()
    assert document == {
        "host": "db.invalid",
        "engine": "exampledb",
        "version": "3",
        "version_source": "profile_default",
        "environment": "production",
        "instance": "main",
        "port": 6432,
    }


def test_a_request_reads_as_itself() -> None:
    assert str(request()) == "exampledb 3, instance main"


# --------------------------------------------------------------------------- the paths


def test_placeholders_are_substituted_from_the_request() -> None:
    paths = resolve_paths(PROFILE, request(instance="reporting"))
    assert paths["data"].path == "/var/lib/basewright/exampledb/reporting/data"
    assert paths["log"].path == "/var/log/basewright/exampledb/reporting"


def test_every_declared_path_is_resolved() -> None:
    assert set(resolve_paths(PROFILE, request())) == {"data", "journal", "log", "backup"}


def test_a_path_carries_what_the_layout_said_about_it() -> None:
    backup = resolve_paths(PROFILE, request())["backup"]
    assert backup.mode == "0750"
    assert backup.min_free == "50GB"
    assert backup.min_free_bytes == 50_000_000_000
    assert backup.prefer_separate_from == ("data",)


def test_a_path_without_a_minimum_says_so_rather_than_guessing() -> None:
    paths = resolve_paths(PROFILE, request())
    assert paths["data"].min_free_bytes == 20_000_000_000
    assert resolve_path("/opt/{{ engine }}", request()) == "/opt/exampledb"


def test_the_version_is_a_placeholder_too() -> None:
    assert resolve_path("/opt/{{ engine }}-{{ version }}", request()) == "/opt/exampledb-3"


def test_space_inside_the_braces_is_allowed() -> None:
    assert resolve_path("/opt/{{engine}}/{{  instance  }}", request()) == "/opt/exampledb/main"


def test_a_placeholder_nobody_defined_is_an_error() -> None:
    """A directory called '{{ instnace }}' would be created without complaint."""
    with pytest.raises(PlaceholderError, match="not a placeholder a path has"):
        resolve_path("/opt/{{ instnace }}", request())


def test_the_error_lists_the_placeholders_there_are() -> None:
    with pytest.raises(PlaceholderError, match="engine, instance, version"):
        resolve_path("/opt/{{ nonsense }}", request())


def test_an_unclosed_placeholder_is_an_error() -> None:
    with pytest.raises(PlaceholderError, match="was not closed"):
        resolve_path("/opt/{{ engine }", request())


def test_a_relative_path_is_an_error() -> None:
    with pytest.raises(LayoutError, match="not an absolute path"):
        resolve_path("var/lib/{{ engine }}", request())


def test_a_path_reads_as_itself() -> None:
    assert str(resolve_paths(PROFILE, request())["data"]).startswith("data /var/lib")
