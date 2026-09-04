"""Finding the profile for an engine somebody named.

``--profile`` takes a path and always will: it is how a profile author runs one that is
not committed yet, and how every fixture in this repository is driven. But naming a
directory is not how an operator thinks about it. They know which engine they are
provisioning, and looking it up under ``profiles/`` is a lookup rather than a decision --
which is the only reason the core is allowed to do it at all.

Nothing here knows what any engine is called. It reads the directory and reports what is
in it, so an operator who mistypes a name is told which names exist rather than told to go
and look.
"""

from __future__ import annotations

from pathlib import Path

from basewright.profiles.errors import ProfileError
from basewright.report.problems import display

#: Where profiles are looked for, in order. The first is the copy inside an installed
#: wheel; the second is the repository, which is what a development checkout has. Mirrors
#: how the schemas are found, because it is the same problem.
_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "_profiles",
    Path(__file__).resolve().parents[2] / "profiles",
)


class UnknownEngineError(ProfileError):
    """An engine named on the command line that no profile describes."""


def profiles_directory() -> Path:
    """Where the profiles that ship with this installation live."""
    for candidate in _CANDIDATES:
        if candidate.is_dir():
            return candidate
    looked = ", ".join(display(candidate) for candidate in _CANDIDATES)
    raise UnknownEngineError(f"no profiles directory found; looked in: {looked}")


def known_engines() -> list[str]:
    """The engines this installation can provision, in a stable order."""
    try:
        directory = profiles_directory()
    except UnknownEngineError:
        return []
    return sorted(child.name for child in directory.iterdir() if child.is_dir())


def directory_for(engine: str) -> Path:
    """The profile directory for one engine, or a refusal naming the ones there are."""
    directory = profiles_directory() / engine
    if directory.is_dir():
        return directory

    known = known_engines()
    available = ", ".join(known) if known else "none, which is why this is failing"
    raise UnknownEngineError(
        f"no profile for {engine!r}. The engines this installation can provision are: "
        f"{available}. Adding one means adding a directory under "
        f"{display(profiles_directory())}/, never editing the core -- see "
        f"docs/dev/writing-a-profile.md."
    )
