"""The picture of a profile has to describe the profile that exists.

A diagram is the part of the documentation nobody rereads when the format changes, which
is exactly why it is checked mechanically rather than by intention. The renderer holds one
list of the files a profile is made of and the loader holds another; if they ever disagree,
the build says so rather than the README quietly describing a format nobody ships.
"""

from __future__ import annotations

import sys
from pathlib import Path

from basewright.profiles.schema import PROFILE_FILES, schema_directory, schema_name_for

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from render_assets import PROFILE_ANATOMY  # noqa: E402


def test_the_diagram_lists_the_files_a_profile_is_made_of() -> None:
    drawn = tuple(name for name, _, _ in PROFILE_ANATOMY)

    assert drawn == PROFILE_FILES, (
        "The profile anatomy diagram in tools/render_assets.py lists a different set of "
        "files than the loader reads. One of the two is out of date."
    )


def test_every_file_the_diagram_draws_is_validated() -> None:
    """A file in the picture with no schema is a file nothing checks."""
    for name, _, _ in PROFILE_ANATOMY:
        assert (schema_directory() / schema_name_for(name)).is_file()


def test_every_file_the_diagram_draws_says_who_reads_it() -> None:
    """A file whose consumer nobody can name is a file with no reason to exist."""
    for name, declares, reader in PROFILE_ANATOMY:
        assert declares, f"{name} is drawn without saying what it declares"
        assert reader, f"{name} is drawn without saying which step reads it"
