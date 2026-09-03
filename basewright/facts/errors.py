"""What a rejected facts document says for itself.

Same treatment a bad profile gets, and for the same reason: whoever wrote the collector is
not whoever wrote the code refusing its output, so the refusal has to name the place and
the remedy. The rendering is shared, in :mod:`basewright.report.problems`.
"""

from __future__ import annotations

from pathlib import Path

from basewright.report.problems import Problem, display, render_problems


class FactsError(Exception):
    """Base class for everything that stops facts from being read."""


class MissingFactsError(FactsError):
    """There is no facts document at that path."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"{display(path)} is not a facts document")


class InvalidFactsError(FactsError):
    """The document is there and does not describe a machine that could exist.

    Facts that contradict themselves are worth refusing rather than working around. A
    mount with more free space than it has is a collector bug, and every number that
    collector produced is now in question -- including the ones a plan would be sized
    against.
    """

    def __init__(self, path: Path, problems: list[Problem]) -> None:
        self.path = path
        self.problems = sorted(problems)
        super().__init__(self.report())

    def report(self) -> str:
        return render_problems(self.path, "facts document", self.problems)
