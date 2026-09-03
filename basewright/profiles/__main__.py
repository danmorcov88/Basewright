"""Validate profile directories from the command line.

    python -m basewright.profiles PATH [PATH ...]
    python -m basewright.profiles --all profiles

This is not one of the verbs. The verbs act on a host; this acts on the repository, and
exists because the schema is only useful if the person writing a profile can run it
against their work before a pull request does. It is also what checks every profile in the
repository on every build.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from basewright.cli import EXIT_OK, EXIT_REFUSED, EXIT_USAGE
from basewright.profiles.errors import InvalidProfileError, MissingProfileError, ProfileError
from basewright.profiles.loader import load_profile, profile_directories
from basewright.profiles.model import Profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m basewright.profiles",
        description="Validate one or more profiles against the profile schema.",
    )
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="+",
        type=Path,
        help="A profile directory, or with --all a directory of profile directories.",
    )
    parser.add_argument(
        "--all",
        dest="every",
        action="store_true",
        help="Treat each PATH as a directory whose subdirectories are the profiles.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        targets = _targets(args.paths, every=args.every)
    except MissingProfileError as error:
        print(error, file=sys.stderr)
        return EXIT_USAGE

    if not targets:
        for path in args.paths:
            print(f"{_display(path)} holds no profiles yet.")
        return EXIT_OK

    refused = 0
    for target in targets:
        try:
            print(_summary(load_profile(target)))
        except InvalidProfileError as error:
            print(error.report(), file=sys.stderr)
            print("", file=sys.stderr)
            refused += 1
        except ProfileError as error:
            print(error, file=sys.stderr)
            refused += 1

    if refused:
        checked = len(targets)
        print(f"{refused} of {checked} profiles were refused.", file=sys.stderr)
        return EXIT_REFUSED
    return EXIT_OK


def _targets(paths: Sequence[Path], *, every: bool) -> list[Path]:
    if not every:
        return list(paths)
    return [child for path in paths for child in profile_directories(path)]


def _summary(profile: Profile) -> str:
    """One line per profile: enough to see that the right thing was read."""
    parts = (
        f"{len(profile.versions)} versions",
        f"{len(profile.os_families)} families",
        f"{len(profile.gates)} gates",
        f"{len(profile.sizing)} sizing rules",
        f"{len(profile.checks)} checks",
    )
    return (
        f"{_display(profile.root)}  valid -- "
        f"{profile.display_name} profile {profile.profile_version}, {', '.join(parts)}"
    )


def _display(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path.as_posix()
    return relative.as_posix() or "."


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
