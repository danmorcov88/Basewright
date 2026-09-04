"""Which schema describes which file of a profile.

The machinery that reads and applies a schema is in :mod:`basewright.schema`, because a
facts document and a plan are validated by exactly the same code. What is particular to a
profile is the list of files it is made of, and that is here.
"""

from __future__ import annotations

from basewright.schema import problems_in, schema_directory

__all__ = ["PROFILE_FILES", "problems_in", "schema_directory", "schema_name_for"]

#: The files a profile is made of, in the order they are read and reported.
PROFILE_FILES: tuple[str, ...] = (
    "profile.yml",
    "support-matrix.yml",
    "requirements.yml",
    "layout.yml",
    "sizing.yml",
    "packages.yml",
    "apply.yml",
    "verify.yml",
)


def schema_name_for(profile_file: str) -> str:
    """Return the schema document that describes one file of a profile."""
    return profile_file.replace(".yml", ".schema.json")
