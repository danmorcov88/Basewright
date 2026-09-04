"""``python -m basewright.profiles`` -- the command a profile author runs before a review.

It is not one of the verbs: the verbs act on a host, this acts on the repository. It
exists because a schema is only a specification if the person writing against it can check
their work, and because the build needs something to run over every profile that lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from basewright.cli import EXIT_OK, EXIT_REFUSED, EXIT_USAGE
from basewright.profiles.__main__ import main

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "test" / "fixtures" / "profiles"


def test_a_valid_profile_is_reported_in_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([str(FIXTURES / "exampledb")])

    printed = capsys.readouterr().out
    assert code == EXIT_OK
    assert printed.count("\n") == 1
    assert "valid" in printed
    assert "6 sizing rules" in printed


def test_an_invalid_profile_is_refused_with_its_report(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([str(FIXTURES / "malformed")])

    refusal = capsys.readouterr().err
    assert code == EXIT_REFUSED
    assert "rules[0].severity" in refusal
    assert "1 of 1 profiles were refused." in refusal


def test_several_profiles_are_all_checked_before_the_run_gives_up(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stopping at the first bad profile makes fixing a tree an exercise in patience."""
    code = main([str(FIXTURES / "malformed"), str(FIXTURES / "inconsistent")])

    refusal = capsys.readouterr().err
    assert code == EXIT_REFUSED
    assert "malformed is not a valid profile" in refusal
    assert "inconsistent is not a valid profile" in refusal
    assert "2 of 2 profiles were refused." in refusal


def test_a_tree_with_no_profiles_says_so_rather_than_passing_quietly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check that silently found nothing is a check nobody can tell is working."""
    code = main(["--all", str(tmp_path)])

    assert code == EXIT_OK
    assert "holds no profiles yet." in capsys.readouterr().out


def test_a_tree_is_walked_one_profile_deep(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import shutil

    shutil.copytree(FIXTURES / "exampledb", tmp_path / "one")
    shutil.copytree(FIXTURES / "malformed", tmp_path / "two")

    code = main(["--all", str(tmp_path)])

    captured = capsys.readouterr()
    assert code == EXIT_REFUSED
    assert "valid" in captured.out
    assert "1 of 2 profiles were refused." in captured.err


def test_a_path_that_is_not_there_is_a_usage_error(tmp_path: Path) -> None:
    assert main(["--all", str(tmp_path / "nowhere")]) == EXIT_USAGE
