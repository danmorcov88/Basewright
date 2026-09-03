"""What a rejected document says for itself.

Two things get read from disk and refused: a profile, written by whoever knows the engine,
and a facts document, written by whoever wrote the collector. Neither author is the person
who wrote the code doing the refusing, so a rejection has to carry four things — the file,
the place inside it, what is wrong, and what to do about it. Anything less turns a
specification into a guessing game.

Both refusals are rendered here, once, because the alternative is two renderers that have
to be kept in step by hand and eventually are not.
"""

from __future__ import annotations

import textwrap
from collections.abc import Sequence
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
class Problem:
    """One reason a document was rejected.

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


def render_problems(subject: Path, noun: str, problems: Sequence[Problem]) -> str:
    """Render every problem, grouped by file, in the order they are fixed in."""
    count = len(problems)
    plural = "problem" if count == 1 else "problems"
    lines = [f"{display(subject)} is not a valid {noun} -- {count} {plural}."]

    width = _column_width(problems)
    current_file = ""
    for problem in problems:
        if problem.file != current_file:
            current_file = problem.file
            lines.append("")
            lines.append(f"  {current_file}")
        location = problem.location or "(document)"
        lines.append(f"    {location.ljust(width)}  {problem.message}")
        lines.extend(_wrapped_hint(problem.hint))

    return "\n".join(lines)


def display(path: Path) -> str:
    """Render a path the same way on every machine.

    Reports are compared byte for byte by the documentation asset check, and read by
    people on three operating systems. Absolute paths would make both harder for no gain.
    """
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path.as_posix()
    return relative.as_posix() or "."


def _column_width(problems: Sequence[Problem]) -> int:
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
