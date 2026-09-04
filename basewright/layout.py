"""Turning the paths a profile declares into the paths a host will actually have.

A layout is written once, for every instance the engine will ever provision, so it names
what varies rather than repeating it::

    default: /var/lib/basewright/{{ engine }}/{{ instance }}/data

Substitution is all this does. There are three placeholders, they are replaced with
values from the resolved request, and a placeholder that is not one of the three is an
error rather than something left in the path -- a directory called ``{{ instnace }}``
would be created without complaint by anything downstream, and found six months later.

This is not templating. There is no logic here and there is not going to be any: the
paths in a plan are decided in Python, the same as every other value in it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from basewright.profiles.model import PathSpec, Profile
from basewright.request import Request
from basewright.units import parse_bytes

#: ``{{ name }}``, with any amount of space inside the braces, as a profile writes it.
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


class LayoutError(ValueError):
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
    values: Mapping[str, str] = {
        "engine": request.engine,
        "instance": request.instance,
        "version": request.version,
    }

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            known = ", ".join(sorted(values))
            raise LayoutError(
                f"{default!r} uses {{{{ {name} }}}}, which is not a placeholder a path has. "
                f"The ones a path has are: {known}."
            )
        return values[name]

    resolved = _PLACEHOLDER.sub(replace, default)
    if "{{" in resolved or "}}" in resolved:
        raise LayoutError(
            f"{default!r} has a placeholder that was not closed. Write it as {{{{ name }}}}."
        )
    if not resolved.startswith("/"):
        raise LayoutError(
            f"{default!r} resolves to {resolved!r}, which is not an absolute path. Every path "
            "in a plan is absolute, because apply runs it from somewhere nobody chose."
        )
    return resolved


def unknown_purposes(spec: PathSpec, purposes: Mapping[str, object]) -> list[str]:
    """Any purpose the path prefers to be separate from that the layout does not define."""
    return sorted(name for name in spec.prefer_separate_from if name not in purposes)
