"""Command line entry point.

The CLI is deliberately thin. It parses arguments, hands them to the library, and
renders whatever comes back. Every decision it appears to make is made under
``basewright/`` and is tested without a terminal.

There is no ``apply`` verb here on purpose: this package decides, Ansible acts.

What this module does own is the exit codes. They are a contract with Semaphore, which
marks a task red on anything non-zero, and they are set out in ``EXIT_CODES`` below and
in ADR-0019 rather than left as four constants nobody wrote down.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from basewright import __version__
from basewright.facts import FactsError, HostFacts, load_facts
from basewright.facts.errors import InvalidFactsError
from basewright.placeholders import PlaceholderError
from basewright.planner import (
    PlanError,
    build_plan,
    content_of,
    plan_id_for,
    plan_problems,
    rendered,
)
from basewright.preflight import RuleError, document, evaluate
from basewright.profiles import (
    InvalidProfileError,
    ProfileError,
    directory_for,
    known_engines,
    load_profile,
)
from basewright.profiles.model import Profile
from basewright.report.plan import render_plan
from basewright.report.preflight import render_preflight
from basewright.report.problems import REPORT_WIDTH, display, render_problems, wrapped
from basewright.request import Request, RequestError, resolve_request
from basewright.units import render_bytes

#: Everything went as planned.
EXIT_OK = 0
#: A gate blocked, a document was read and is not acceptable, or verification found a
#: mismatch. An expected, reportable outcome, and there is a report explaining it.
EXIT_REFUSED = 2
#: The request itself is malformed, or an input could not be read at all.
EXIT_USAGE = 64
#: The verb exists but is not built yet. Removed as the roadmap closes.
EXIT_UNIMPLEMENTED = 69


@dataclass(frozen=True)
class ExitCode:
    """One exit code: what produced it, and what to do about it."""

    #: The number the process exits with.
    code: int
    #: What happened, in the terms the person reading a task log thinks in.
    meaning: str
    #: What that person does next. This is the reason the code exists at all.
    response: str


#: The exit codes, as a set rather than four scattered constants (ADR-0019).
#:
#: Semaphore marks a task red on any non-zero code, so the number is not how a run is
#: reported as failed -- the report already does that. What the number carries is what
#: the person reading the red task is meant to do next, and there are four answers worth
#: telling apart.
#:
#: One line inside that is worth stating out loud, because it is what decides between the
#: two non-zero answers: **a file that could not be read at all is a usage error, and a
#: file that was read and is not acceptable is a refusal.** A missing facts document is
#: 64; one that fails its contract is 2. A plan whose id no longer matches its content is
#: 2 as well -- it is a plan, it is simply not the plan it claims to be, and there is a
#: report saying which.
EXIT_CODES: tuple[ExitCode, ...] = (
    ExitCode(
        EXIT_OK,
        "The tool ran, and the answer is yes.",
        "Go on to the next step.",
    ),
    ExitCode(
        EXIT_REFUSED,
        "The tool ran, and the answer is no.",
        "Read the report: it names the rule, what was found, and the way out.",
    ),
    ExitCode(
        EXIT_USAGE,
        "The request itself is malformed.",
        "Fix the command. Nothing was decided, so there is no report to read.",
    ),
    ExitCode(
        EXIT_UNIMPLEMENTED,
        "The verb exists and is not built yet.",
        "Nothing yet. docs/dev/STATUS.md says what is built.",
    ),
)

#: The verbs that exist as an interface and are not built. Named here rather than in the
#: two places that need it, so that a verb which starts working cannot go on declaring no
#: inputs while still exiting 69.
UNBUILT: frozenset[str] = frozenset({"verify"})

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

#: Two ways to say the same thing, and they are not interchangeable in intent.
#:
#: ``--engine`` is what an operator uses: they know which engine they are provisioning and
#: not where its directory lives. ``--profile`` is what a profile author uses, and it is
#: how every fixture in this repository is driven -- a profile that is not committed yet
#: has no name to look up. Neither replaces the other, which is why both are here.
_ENGINE_HELP = "The engine to provision, looked up under profiles/."
_PROFILE_HELP = "Path to a profile directory, for one that is not installed under profiles/."

#: Reading a plan back is what makes it reviewable by somebody other than the person who
#: produced it, which is the separation the whole artifact exists for. Retrieval by plan
#: id needs a plan store and belongs to a later phase; this takes a path.
_FROM_HELP = "Render a plan that already exists, instead of producing one."

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
        _add_arguments(sub, verb)
    return parser


def _add_arguments(parser: argparse.ArgumentParser, verb: str) -> None:
    """Give a verb exactly the inputs it reads, and nothing it does not.

    Built per verb rather than in one loop over all of them, because ``--help`` is a
    published contract: it is captured into the documentation and an operator writes a
    Semaphore template against it. A flag no implementation will ever read is a promise
    the help page cannot keep.
    """
    if verb in UNBUILT:
        # An unbuilt verb declares no inputs. Verify reads a plan and a live instance,
        # and reaching a live instance runs over SSH or WinRM, which is Ansible's half
        # of the split -- so its flags arrive with it rather than being guessed at now
        # and lived with afterwards.
        return

    parser.add_argument("--facts", metavar="PATH", type=Path, help=_FACTS_HELP)
    if verb in {"preflight", "plan"}:
        _add_request_arguments(parser)
    if verb == "plan":
        parser.add_argument("--from", dest="from_plan", metavar="PATH", type=Path, help=_FROM_HELP)
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit the machine-readable artifact instead of the console rendering.",
    )


def _add_request_arguments(parser: argparse.ArgumentParser) -> None:
    """What is being asked for, beyond the host the facts describe.

    Everything not given here comes from the profile's defaults, and the difference is
    recorded: a version a person chose and a version nobody chose are not the same
    decision, and one of the rules reads which it was.
    """
    # Mutually exclusive, because a request that named both would have to be resolved by
    # a precedence rule, and a precedence rule is a thing somebody eventually relies on
    # without meaning to.
    named = parser.add_mutually_exclusive_group()
    named.add_argument("--engine", metavar="NAME", help=_ENGINE_HELP)
    named.add_argument("--profile", metavar="PATH", type=Path, help=_PROFILE_HELP)
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

    _refuse(f"basewright {args.verb}: not built yet -- see docs/dev/STATUS.md for the roadmap.")
    return EXIT_UNIMPLEMENTED


def gather(facts: Path | None, *, as_json: bool) -> int:
    """Read a facts document, normalize it, and say what the host is."""
    if facts is None:
        _refuse(
            "basewright gather: --facts is required. Collecting from a live host runs over "
            "SSH and is not built yet -- see docs/dev/STATUS.md."
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
    if args.from_plan is not None:
        return render_existing(args)

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
        print(render_plan(artifact))
    return EXIT_OK


def render_existing(args: argparse.Namespace) -> int:
    """Read a plan somebody else produced, check it is intact, and render it.

    The check is not ceremony. A plan is named after a digest of its own content, so a
    plan whose id does not match what it says has been edited since it was produced --
    and the person about to approve it is entitled to be told that rather than to read
    the edited version as though it were the artifact.
    """
    conflicting = [
        name
        for name, value in (
            ("--facts", args.facts),
            ("--engine", args.engine),
            ("--profile", args.profile),
            ("--json", args.as_json or None),
        )
        if value
    ]
    if conflicting:
        _refuse(
            f"basewright plan: --from cannot be combined with {', '.join(conflicting)}. "
            "Reading a plan and producing one are different jobs, and the file --from "
            "names is already the machine-readable artifact."
        )
        return EXIT_USAGE

    try:
        document = json.loads(args.from_plan.read_text(encoding="utf-8"))
    except OSError as error:
        _refuse(f"basewright plan: cannot read {display(args.from_plan)}: {error}")
        return EXIT_USAGE
    except json.JSONDecodeError as error:
        _refuse(f"basewright plan: {display(args.from_plan)} is not readable JSON: {error}")
        return EXIT_REFUSED

    problems = plan_problems(document)
    if problems:
        print(render_problems(args.from_plan, "plan", problems), file=sys.stderr)
        return EXIT_REFUSED

    claimed = document["plan_id"]
    actual = plan_id_for(content_of(document))
    if claimed != actual:
        _refuse(
            f"basewright plan: {display(args.from_plan)} calls itself {claimed}, but its "
            f"content produces {actual}. A plan is named after a digest of what it says, "
            f"so this one has been edited since it was produced. Produce a fresh plan "
            f"rather than applying this."
        )
        return EXIT_REFUSED

    print(render_plan(document))
    return EXIT_OK


def _inputs(args: argparse.Namespace, verb: str) -> tuple[HostFacts, Profile, Request] | int:
    """Read the facts, the profile and the request, or say why none of them was read.

    Shared by the two verbs that need all three, so that a malformed profile is refused
    in the same words whichever of them was asked for.
    """
    if args.facts is None or (args.engine is None and args.profile is None):
        engines = ", ".join(known_engines()) or "none are installed"
        _refuse(
            f"basewright {verb}: --facts, and one of --engine or --profile, are required. "
            f"The engines this installation can provision are: {engines}. A facts "
            "document is written by ansible/playbooks/gather.yml."
        )
        return EXIT_USAGE

    try:
        directory = directory_for(args.engine) if args.engine else args.profile
    except ProfileError as error:
        _refuse(f"basewright {verb}: {error}")
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
        profile = load_profile(directory)
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


def _refuse(message: str) -> None:
    """Print a refusal, wrapped the way every other report in the project is.

    A refusal is read in a terminal and in a task log, and captured into a documentation
    image. None of the three wraps kindly on its own.
    """
    for line in wrapped(message, width=REPORT_WIDTH):
        print(line, file=sys.stderr)


#: How far the label column runs, so a folded list lines up under itself rather than under
#: its label.
_FACT_INDENT = 18


def _listed(label: str, values: Sequence[str]) -> list[str]:
    """One fact whose value is a short list, folded to the width every report uses.

    A hand-written fixture has one listening port and a real machine has a dozen. On one
    line that is longer than a terminal, which is the kind of thing only running against a
    real machine tells you.
    """
    if not values:
        return [f"  {label:<15} none"]

    indent = " " * _FACT_INDENT
    folded = wrapped(", ".join(values), width=REPORT_WIDTH - _FACT_INDENT)
    return [f"  {label:<15} {folded[0]}", *(f"{indent}{line}" for line in folded[1:])]


def _counted(values: Sequence[str], noun: str) -> str:
    """How many of something, and which ones while that still fits on the line.

    The first real host this was run against reported a hundred and nine services. Naming
    them is forty lines that only a profile could interpret, because the core recognises no
    service by name -- and the rule that can interpret them is in preflight, which names the
    one that matters. A fixture with one service is a different case, and worth spelling
    out. What decides between them is how much fits on a line, which is a fact about the
    page rather than a judgement about the host.
    """
    if not values:
        return "none"

    total = f"{len(values)} {noun}" if len(values) == 1 else f"{len(values)} {noun}s"
    spelled = f"{total}: {', '.join(values)}"
    return spelled if len(spelled) <= REPORT_WIDTH - _FACT_INDENT else total


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

    lines.extend(_listed("listening", [str(port.port) for port in host.listening_ports]))
    installed = [f"{s.name} {s.version or ''}".strip() for s in host.services]
    lines.append(f"  {'installed':<15} {_counted(installed, 'service')}")

    lines.append("")
    lines.append(f"Facts collected {host.collected_at:%Y-%m-%dT%H:%M:%SZ}. Nothing was changed.")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
