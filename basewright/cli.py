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
from basewright.placeholders import PlaceholderError
from basewright.planner import PlanError, build_plan, rendered, summarize
from basewright.preflight import RuleError, document, evaluate
from basewright.profiles import InvalidProfileError, ProfileError, load_profile
from basewright.profiles.model import Profile
from basewright.report.preflight import render_preflight
from basewright.request import Request, RequestError, resolve_request
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

#: No profile ships in the repository yet, so the directory is named rather than looked up
#: by engine. When profiles/ has members, --engine becomes the way this is usually spelled.
_PROFILE_HELP = "Path to the profile directory for the engine being provisioned."

#: The environment an instance belongs to. Nothing gates on it yet; the plan records it,
#: and the strictest of the plausible answers is the safest thing to assume.
DEFAULT_ENVIRONMENT = "production"


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
        if verb in {"preflight", "plan"}:
            _add_request_arguments(sub)
        sub.add_argument(
            "--json",
            dest="as_json",
            action="store_true",
            help="Emit the machine-readable artifact instead of the console rendering.",
        )
    return parser


def _add_request_arguments(parser: argparse.ArgumentParser) -> None:
    """What is being asked for, beyond the host the facts describe.

    Everything not given here comes from the profile's defaults, and the difference is
    recorded: a version a person chose and a version nobody chose are not the same
    decision, and one of the rules reads which it was.
    """
    parser.add_argument("--profile", metavar="PATH", type=Path, help=_PROFILE_HELP)
    parser.add_argument(
        "--engine-version",
        metavar="VERSION",
        dest="engine_version",
        help="The engine version to provision. Defaults to the profile's default version.",
    )
    parser.add_argument(
        "--instance",
        metavar="NAME",
        help="The instance name. Defaults to the profile's default instance.",
    )
    parser.add_argument(
        "--environment",
        metavar="NAME",
        default=DEFAULT_ENVIRONMENT,
        help=f"The environment this instance belongs to. Defaults to {DEFAULT_ENVIRONMENT}.",
    )
    parser.add_argument(
        "--port",
        metavar="PORT",
        type=int,
        help="The port the instance will listen on. Defaults to the profile's default port.",
    )
    parser.add_argument(
        "--host",
        metavar="NAME",
        help="The host being provisioned. Defaults to the host the facts describe.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verb == "gather":
        return gather(args.facts, as_json=args.as_json)

    if args.verb == "preflight":
        return preflight(args)

    if args.verb == "plan":
        return plan(args)

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


def preflight(args: argparse.Namespace) -> int:
    """Evaluate every rule against one host, and say what they came to."""
    prepared = _inputs(args, "preflight")
    if isinstance(prepared, int):
        return prepared
    host, profile, request = prepared

    try:
        result = evaluate(host, profile, request)
    except RuleError as error:
        print(error, file=sys.stderr)
        return EXIT_REFUSED

    if args.as_json:
        print(json.dumps(document(result, profile, request), indent=2, sort_keys=True))
    else:
        rendering = render_preflight(result)
        print(rendering, file=sys.stderr if result.blocked else sys.stdout)

    return EXIT_REFUSED if result.blocked else EXIT_OK


def plan(args: argparse.Namespace) -> int:
    """Render the intended end state, or refuse and say what would have to change.

    Preflight runs first, and a block ends it here. There is no partial plan and no flag
    that produces one: a host that cannot carry the instance is reported as refused, with
    the rule and the way out, rather than as a plan somebody might apply anyway.
    """
    prepared = _inputs(args, "plan")
    if isinstance(prepared, int):
        return prepared
    host, profile, request = prepared

    try:
        gates = evaluate(host, profile, request)
    except RuleError as error:
        print(error, file=sys.stderr)
        return EXIT_REFUSED

    if gates.blocked:
        # The refusal report already says that no plan was produced and that nothing
        # produces one anyway. Saying it twice would read as two different refusals.
        print(render_preflight(gates), file=sys.stderr)
        return EXIT_REFUSED

    try:
        artifact = build_plan(host, profile, request, gates)
    except (PlanError, PlaceholderError) as error:
        print(error, file=sys.stderr)
        return EXIT_REFUSED

    if args.as_json:
        print(rendered(artifact), end="")
    else:
        print(summarize(artifact))
    return EXIT_OK


def _inputs(args: argparse.Namespace, verb: str) -> tuple[HostFacts, Profile, Request] | int:
    """Read the facts, the profile and the request, or say why none of them was read.

    Shared by the two verbs that need all three, so that a malformed profile is refused
    in the same words whichever of them was asked for.
    """
    if args.facts is None or args.profile is None:
        print(
            f"basewright {verb}: --facts and --profile are both required. Collecting "
            "facts from a live host runs over SSH and is not built yet -- see "
            "docs/dev/STATUS.md.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        host = load_facts(args.facts)
    except InvalidFactsError as error:
        print(error.report(), file=sys.stderr)
        return EXIT_REFUSED
    except FactsError as error:
        print(error, file=sys.stderr)
        return EXIT_USAGE

    try:
        profile = load_profile(args.profile)
    except InvalidProfileError as error:
        print(error.report(), file=sys.stderr)
        return EXIT_REFUSED
    except ProfileError as error:
        print(error, file=sys.stderr)
        return EXIT_USAGE

    try:
        request = resolve_request(
            profile,
            host=args.host or host.host,
            version=args.engine_version,
            environment=args.environment,
            instance=args.instance,
            port=args.port,
        )
    except RequestError as error:
        print(error, file=sys.stderr)
        return EXIT_REFUSED

    return host, profile, request


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
