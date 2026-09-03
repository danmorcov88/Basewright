"""What a rejected profile says for itself.

A profile is the contribution surface of this project, and the person writing one is
usually not the person who wrote the loader. So a rejection has to carry four things: the
file, the place inside it, what is wrong, and what to do about it. Anything less makes the
schema a wall rather than a specification.

The remedy is taken from the schema's own ``description`` wherever there is one, so the
documentation a profile author is pointed at and the documentation the schema carries
cannot drift apart -- they are the same string.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

#: Width of the location column, clamped so that one long location cannot push every
#: message on the report off the right-hand edge.
_LOCATION_WIDTH = (18, 22)

#: Width the whole report is wrapped to. A refusal is read in a terminal and in a task
#: log, and neither of them wraps kindly.
_REPORT_WIDTH = 88

#: Indent of the remedy under its message. Fixed rather than aligned to the location
#: column, so two reports side by side in one log still line up with each other.
_HINT_INDENT = 6


@dataclass(frozen=True, order=True)
class ProfileProblem:
    """One reason a profile was rejected.

    ``file`` and ``location`` are ordered first so that sorting a list of problems groups
    them by file and then by position, which is the order a person fixes them in.
    """

    file: str
    location: str
    message: str
    hint: str = ""

    def __str__(self) -> str:
        where = f"{self.file}:{self.location}" if self.location else self.file
        return f"{where} {self.message}"


class ProfileError(Exception):
    """Base class for everything that stops a profile from being loaded."""


class MissingProfileError(ProfileError):
    """The directory is not there, or is not a directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        super().__init__(f"{_display(directory)} is not a profile directory")


class InvalidProfileError(ProfileError):
    """The profile is there and does not hold together.

    Every problem found is reported at once. Fixing a profile one error per run is the
    experience this class exists to avoid.
    """

    def __init__(self, directory: Path, problems: list[ProfileProblem]) -> None:
        self.directory = directory
        self.problems = sorted(problems)
        super().__init__(self.report())

    def report(self) -> str:
        """Render every problem, grouped by file, in the order they are fixed in."""
        count = len(self.problems)
        plural = "problem" if count == 1 else "problems"
        lines = [f"{_display(self.directory)} is not a valid profile -- {count} {plural}."]

        width = _column_width(self.problems)
        current_file = ""
        for problem in self.problems:
            if problem.file != current_file:
                current_file = problem.file
                lines.append("")
                lines.append(f"  {current_file}")
            location = problem.location or "(document)"
            lines.append(f"    {location.ljust(width)}  {problem.message}")
            lines.extend(_wrapped_hint(problem.hint))

        return "\n".join(lines)


def _column_width(problems: list[ProfileProblem]) -> int:
    """Width of the location column: the longest location, within fixed bounds."""
    lower, upper = _LOCATION_WIDTH
    longest = max((len(p.location or "(document)") for p in problems), default=lower)
    return min(max(longest, lower), upper)


def _wrapped_hint(hint: str) -> list[str]:
    """Wrap a remedy under its message at a fixed indent."""
    if not hint:
        return []
    indent = " " * _HINT_INDENT
    wrapped = textwrap.wrap(" ".join(hint.split()), width=_REPORT_WIDTH - _HINT_INDENT - 3)
    return [f"{indent}{'->' if index == 0 else '  '} {line}" for index, line in enumerate(wrapped)]


def _display(path: Path) -> str:
    """Render a path the same way on every machine.

    Reports are compared byte for byte by the documentation asset check, and read by
    people on three operating systems. Absolute paths would make both harder for no gain.
    """
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path.as_posix()
    return relative.as_posix() or "."
