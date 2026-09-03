"""Command line entry point.

The CLI is deliberately thin. It parses arguments, hands them to the library, and
renders whatever comes back. Every decision it appears to make is made under
``basewright/`` and is tested without a terminal.

There is no ``apply`` verb here on purpose: this package decides, Ansible acts.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from basewright import __version__
from basewright.facts import FactsError, HostFacts, load_facts
from basewright.facts.errors import InvalidFactsError
from basewright.units import render_bytes

#: Everything went as planned.
EXIT_OK = 0
#: A gate blocked, or verification found a mismatch. An expected, reportable outcome.
EXIT_REFUSED = 2
#: The request itself is malformed.
EXIT_USAGE = 64
#: The verb exists but is not built yet. Removed as the roadmap closes.
EXIT_UNIMPLEMENTED = 69

VERBS: dict[str, str] = {
    "gather": "Read and normalize the facts a host reported. Changes nothing.",
    "preflight": "Evaluate the gate rules against the facts and the request.",
    "plan": "Render the intended end state, every value annotated with its rule.",
    "verify": "Read a live instance back and compare it to the plan it came from.",
}

#: Collecting facts from a live host runs over SSH or WinRM, which is Ansible's half of
#: the split. Until that playbook exists, every verb reads a document instead, and the
#: help says so rather than implying a machine is being contacted.
_FACTS_HELP = "Path to a facts document. Collecting from a live host is not built yet."


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
        sub.add_argument("--facts", metavar="PATH", type=Path, help=_FACTS_HELP)
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

    if args.verb == "gather":
        return gather(args.facts, as_json=args.as_json)

    print(
        f"basewright {args.verb}: not built yet -- see docs/dev/STATUS.md for the roadmap.",
        file=sys.stderr,
    )
    return EXIT_UNIMPLEMENTED


def gather(facts: Path | None, *, as_json: bool) -> int:
    """Read a facts document, normalize it, and say what the host is."""
    if facts is None:
        print(
            "basewright gather: --facts is required. Collecting from a live host runs over "
            "SSH and is not built yet -- see docs/dev/STATUS.md.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        host = load_facts(facts)
    except InvalidFactsError as error:
        print(error.report(), file=sys.stderr)
        return EXIT_REFUSED
    except FactsError as error:
        print(error, file=sys.stderr)
        return EXIT_USAGE

    if as_json:
        print(json.dumps(host.plan_section(), indent=2, sort_keys=True))
    else:
        print(render(host))
    return EXIT_OK


def render(host: HostFacts) -> str:
    """A short summary of what the host is.

    Deliberately short. The rendering that carries a decision and the rule behind it is
    the reporter's, and writing half of it here would mean writing it twice.
    """
    lines = [
        f"HOST  {host.host}",
        f"  os              {host.os}",
        f"  arch            {host.arch}",
        f"  cpu             {host.cpu.cores} cores",
        f"  memory          {render_bytes(host.memory.total_bytes)}",
    ]

    for index, mount in enumerate(host.mounts):
        label = "storage" if index == 0 else ""
        lines.append(f"  {label:<15} {mount}")

    if host.time_sync is not None:
        state = "synchronized" if host.time_sync.synchronized else "NOT synchronized"
        lines.append(f"  time sync       {host.time_sync.service}, {state}")

    listening = ", ".join(str(port.port) for port in host.listening_ports) or "none"
    lines.append(f"  listening       {listening}")

    installed = ", ".join(f"{s.name} {s.version or ''}".strip() for s in host.services) or "none"
    lines.append(f"  installed       {installed}")

    lines.append("")
    lines.append(f"Facts collected {host.collected_at:%Y-%m-%dT%H:%M:%SZ}. Nothing was changed.")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
