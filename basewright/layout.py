"""Turning the paths a profile declares into the paths a host will actually have.

A layout is written once, for every instance the engine will ever provision, so it names
what varies rather than repeating it::

    default: /var/lib/basewright/{{ engine }}/{{ instance }}/data

Filling those in is :mod:`basewright.placeholders`, which every other templated string in
a profile goes through as well. What is particular to a path is the vocabulary it is
allowed to use -- three names, all of them from the resolved request -- and that the
result has to be absolute, because apply runs it from somewhere nobody chose.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from basewright.placeholders import PlaceholderError, substitute
from basewright.profiles.model import PathSpec, Profile
from basewright.request import Request
from basewright.units import parse_bytes


class LayoutError(PlaceholderError):
    """A path that cannot be resolved: an unknown placeholder, or a relative result."""


@dataclass(frozen=True)
class PlannedPath:
    """One path an instance will use, resolved for one request."""

    purpose: str
    path: str
    mode: str
    min_free: str | None
    prefer_separate_from: tuple[str, ...]
    description: str

    @property
    def min_free_bytes(self) -> int | None:
        """The free space this path requires, in bytes, or None if it states none."""
        return None if self.min_free is None else parse_bytes(self.min_free)

    def __str__(self) -> str:
        return f"{self.purpose} {self.path}"


def resolve_paths(profile: Profile, request: Request) -> dict[str, PlannedPath]:
    """Every path the profile declares, resolved for one request.

    The order is the order the profile wrote them in, because that is the order a person
    chose and every report reads better in it than in an alphabetical one.
    """
    return {
        purpose: PlannedPath(
            purpose=purpose,
            path=resolve_path(spec.default, request),
            mode=spec.mode,
            min_free=spec.min_free,
            prefer_separate_from=spec.prefer_separate_from,
            description=spec.description,
        )
        for purpose, spec in profile.paths.items()
    }


def resolve_path(default: str, request: Request) -> str:
    """Substitute the placeholders in one declared path."""
    values: Mapping[str, str | None] = {
        "engine": request.engine,
        "instance": request.instance,
        "version": request.version,
    }

    resolved = substitute(default, values, noun="a path")
    if not resolved.startswith("/"):
        raise LayoutError(
            f"{default!r} resolves to {resolved!r}, which is not an absolute path. Every path "
            "in a plan is absolute, because apply runs it from somewhere nobody chose."
        )
    return resolved


def unknown_purposes(spec: PathSpec, purposes: Mapping[str, object]) -> list[str]:
    """Any purpose the path prefers to be separate from that the layout does not define."""
    return sorted(name for name in spec.prefer_separate_from if name not in purposes)
