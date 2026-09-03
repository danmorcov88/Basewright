"""The CLI is a thin shell: it should parse, dispatch, and nothing more."""

from __future__ import annotations

import pytest

from basewright import __version__
from basewright.cli import VERBS, build_parser, main


def test_version_is_reported() -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["--version"])
    assert exit_info.value.code == 0


def test_a_verb_is_required() -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args([])
    assert exit_info.value.code != 0


@pytest.mark.parametrize("verb", sorted(VERBS))
def test_every_verb_parses(verb: str) -> None:
    assert build_parser().parse_args([verb]).verb == verb


def test_apply_is_not_a_verb_of_this_cli() -> None:
    """Applying is Ansible's job. The split is the architecture, not an omission."""
    assert "apply" not in VERBS


@pytest.mark.parametrize("verb", sorted(VERBS))
def test_unbuilt_verbs_exit_predictably(verb: str) -> None:
    assert main([verb]) == 69


def test_version_string_is_set() -> None:
    assert __version__
