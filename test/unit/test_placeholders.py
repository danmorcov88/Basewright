"""Filling in what a profile leaves open.

Substitution is shared: a path, a package name, a service unit and the location of a
secret all go through it, so the mistakes it can make are made in one place and caught in
one place. The two that matter are a placeholder nobody defined, which is a spelling
mistake in the profile, and one that is defined but was never collected, which is not.
"""

from __future__ import annotations

import pytest

from basewright.placeholders import PlaceholderError, substitute

VALUES = {"engine": "exampledb", "version": "3", "os.codename": "noble", "os.major": None}


def test_a_placeholder_is_replaced() -> None:
    assert substitute("{{ engine }}-server-{{ version }}", VALUES, noun="a package") == (
        "exampledb-server-3"
    )


def test_a_dotted_placeholder_is_replaced() -> None:
    """Repositories are keyed by a code name on one family and by a number on another."""
    assert substitute("{{ os.codename }}", VALUES, noun="a suite") == "noble"


def test_spacing_inside_the_braces_does_not_matter() -> None:
    assert substitute("{{engine}}/{{  version  }}", VALUES, noun="a path") == "exampledb/3"


def test_a_template_with_nothing_open_is_returned_as_it_is() -> None:
    assert substitute("plain", VALUES, noun="a path") == "plain"


def test_an_unknown_placeholder_names_the_ones_that_exist() -> None:
    """A misspelling left in place becomes a directory nobody notices for six months."""
    with pytest.raises(PlaceholderError) as raised:
        substitute("{{ verison }}", VALUES, noun="a path")

    assert "not a placeholder a path has" in str(raised.value)
    assert "engine, os.codename, os.major, version" in str(raised.value)


def test_a_placeholder_the_host_did_not_report_says_so() -> None:
    """A different mistake from a misspelling, so a different message and a different fix."""
    with pytest.raises(PlaceholderError, match="this host did not report"):
        substitute("el{{ os.major }}", VALUES, noun="a repository url")


def test_an_unclosed_placeholder_is_refused() -> None:
    with pytest.raises(PlaceholderError, match="was not closed"):
        substitute("{{ engine }", VALUES, noun="a path")


def test_the_noun_is_what_the_template_is() -> None:
    """The refusal names the thing being written, not the function that was writing it."""
    with pytest.raises(PlaceholderError, match="a secret's location has"):
        substitute("{{ nonsense }}", VALUES, noun="a secret's location")
