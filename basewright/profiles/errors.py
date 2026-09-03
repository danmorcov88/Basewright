"""What a rejected profile says for itself.

The rendering lives in :mod:`basewright.report.problems`, because a facts document is
refused on exactly the same terms and one renderer is easier to keep honest than two.
What is particular to a profile is here: that a directory can be absent, and that a
profile is a thing seven files have to agree about.

The remedy in each problem is taken from the schema's own ``description`` wherever there
is one, so the documentation a profile author is pointed at and the documentation the
schema carries cannot drift apart -- they are the same string.
"""

from __future__ import annotations

from pathlib import Path

from basewright.report.problems import Problem, display, render_problems


class ProfileError(Exception):
    """Base class for everything that stops a profile from being loaded."""


class MissingProfileError(ProfileError):
    """The directory is not there, or is not a directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        super().__init__(f"{display(directory)} is not a profile directory")


class InvalidProfileError(ProfileError):
    """The profile is there and does not hold together.

    Every problem found is reported at once. Fixing a profile one error per run is the
    experience this class exists to avoid.
    """

    def __init__(self, directory: Path, problems: list[Problem]) -> None:
        self.directory = directory
        self.problems = sorted(problems)
        super().__init__(self.report())

    def report(self) -> str:
        return render_problems(self.directory, "profile", self.problems)
