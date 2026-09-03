"""Command line entry point.

The CLI is deliberately thin. It parses arguments, hands them to the library, and
renders whatever comes back. Every decision it appears to make is made under
``basewright/`` and is tested without a terminal.

There is no ``apply`` verb here on purpose: this package decides, Ansible acts.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from basewright import __version__

#: Everything went as planned.
EXIT_OK = 0
#: A gate blocked, or verification found a mismatch. An expected, reportable outcome.
EXIT_REFUSED = 2
#: The request itself is malformed.
EXIT_USAGE = 64
#: The verb exists but is not built yet. Removed as the roadmap closes.
EXIT_UNIMPLEMENTED = 69

VERBS: dict[str, str] = {
    "gather": "Collect and normalize facts from a target host. Changes nothing.",
    "preflight": "Evaluate the gate rules against the facts and the request.",
    "plan": "Render the intended end state, every value annotated with its rule.",
    "verify": "Read a live instance back and compare it to the plan it came from.",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for every verb the tool exposes."""
    parser = argparse.ArgumentParser(
        prog="basewright",
        description=(
            "Turn a server that already exists into a correctly configured database "
            "instance, with the decision-making visible before anything is touched."
        ),
        epilog="Applying a plan is done through the Ansible playbooks, not through this CLI.",
    )
    parser.add_argument("--version", action="version", version=f"basewright {__version__}")

    subcommands = parser.add_subparsers(dest="verb", metavar="VERB", required=True)
    for verb, help_text in VERBS.items():
        sub = subcommands.add_parser(verb, help=help_text, description=help_text)
        sub.add_argument(
            "--facts",
            metavar="PATH",
            help="Path to a facts document, instead of collecting from a host.",
        )
        sub.add_argument(
            "--json",
            dest="as_json",
            action="store_true",
            help="Emit the machine-readable artifact instead of the console rendering.",
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    print(
        f"basewright {args.verb}: not built yet -- see docs/dev/STATUS.md for the roadmap.",
        file=sys.stderr,
    )
    return EXIT_UNIMPLEMENTED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
