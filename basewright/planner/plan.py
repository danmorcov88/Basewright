"""Assembling the plan, and naming it after what it says.

The plan is the product. Everything before it gathers what is true and decides what
follows from it; this is where those become one document that a second person can read,
a change request can carry, and apply can execute without re-deriving anything.

Two properties are worth stating because the code is arranged around them.

**It is deterministic.** The same facts and the same profile produce the same bytes.
Nothing here reads a clock except the one field that records when it was written, nothing
iterates a set, and every list keeps an order somebody chose. That is what makes a golden
plan a review mechanism rather than a test that fails on Tuesdays.

**It is named after its own content.** The identifier is a digest of the plan, computed
over the document *without* the moment it was generated -- which is the one field that
legitimately differs between two runs that decided exactly the same thing. So the
document is assembled first, without that field, the id is taken from it, and only then
are the two put in front. There is no popping a key back out of a finished plan: the
thing the id is computed over never had it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from basewright import __version__
from basewright.facts.model import HostFacts
from basewright.layout import PlannedPath, resolve_paths
from basewright.planner.changes import plan_actions
from basewright.planner.errors import PlanError
from basewright.planner.sizing import evaluate
from basewright.preflight.model import PreflightResult
from basewright.profiles.model import Profile
from basewright.request import Request
from basewright.scope import build_scope

__all__ = ["SCHEMA_VERSION", "build_plan", "plan_id_for", "rendered", "summarize"]

#: The version of the plan contract. Apply refuses a plan whose major version it does not
#: implement, rather than guessing at a field that moved.
SCHEMA_VERSION = "1"

#: How much of the digest the plan is known by. Long enough that two plans in one estate
#: will not collide, short enough to be read out loud from a task log.
_ID_LENGTH = 12


def build_plan(
    facts: HostFacts,
    profile: Profile,
    request: Request,
    preflight: PreflightResult,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Produce the plan for one host, or refuse to produce one at all.

    ``now`` is an argument because the plan records when it was written, and a document
    that cannot be produced twice identically cannot be reviewed by diffing it.
    """
    if preflight.blocked:
        raise PlanError(
            f"{request.host} is blocked by preflight, so there is no plan. A block produces "
            f"a refusal naming the rule and what would have to change; it does not produce "
            f"a partial plan, and there is no flag that makes it one."
        )

    paths = resolve_paths(profile, request)
    scope = build_scope(facts, profile, request, paths)
    parameters = evaluate(profile.sizing, scope)
    actions = plan_actions(facts, profile, request, paths, parameters, scope)

    advisories = sum(1 for parameter in parameters if parameter.advised_against)
    warnings = preflight.warnings + advisories

    body: dict[str, Any] = {
        "profile": {"engine": profile.engine, "version": profile.profile_version},
        "request": request.document(),
        "host": facts.plan_section(),
        "preflight": {
            "summary": preflight.summary,
            "results": [result.document() for result in preflight.results],
        },
        "parameters": [parameter.document() for parameter in parameters],
        "layout": _layout(facts, profile, paths),
        "packages": actions.packages,
        "configuration": list(actions.configuration),
        "tunables": list(actions.tunables),
        "changes": list(actions.changes),
        "secrets": list(actions.secrets),
        "result": {
            "applicable": True,
            "warnings": warnings,
            "warnings_require_acknowledgement": warnings > 0,
        },
    }

    content = {"schema_version": SCHEMA_VERSION, "tool_version": __version__, **body}
    moment = now or datetime.now(UTC)

    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id_for(content),
        "generated_at": f"{moment:%Y-%m-%dT%H:%M:%S}Z",
        "tool_version": __version__,
        **body,
    }


def plan_id_for(content: Mapping[str, Any]) -> str:
    """The name a plan is known by: a digest of everything it says.

    ``content`` is the plan without ``generated_at``, and it has to arrive that way. Two
    runs that reached the same conclusions about the same host produce the same id, so a
    plan can be found again from the id printed in a task log, and a plan that differs
    from the one somebody approved says so in its name.
    """
    if "generated_at" in content:
        raise PlanError(
            "The plan id is computed over the plan without generated_at, which is the one "
            "field two identical plans differ in. Build the document without it."
        )
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_ID_LENGTH]


def rendered(plan: Mapping[str, Any]) -> str:
    """The plan as it is written to a file: one artifact, one set of bytes.

    Keys keep the order the sections were assembled in, which is the order the plan reads
    in. Only the digest sorts them, and it does so on its own.
    """
    return json.dumps(plan, indent=2, ensure_ascii=True) + "\n"


def _layout(facts: HostFacts, profile: Profile, paths: Mapping[str, PlannedPath]) -> dict[str, Any]:
    """Where the instance keeps its files, who owns them, and what carries them.

    The mount is here because free space and failure isolation are properties of the
    filesystem rather than of the directory, and because the person reading the plan six
    months from now will want to know which one filled up.
    """
    account = profile.service_account
    group = account.group or account.name
    return {
        "paths": [_path(facts, planned, account.name, group) for planned in paths.values()],
        "service_account": _account(profile),
    }


def _path(facts: HostFacts, planned: PlannedPath, owner: str, group: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "purpose": planned.purpose,
        "path": planned.path,
        "mode": planned.mode,
        "owner": owner,
        "group": group,
    }
    mount = facts.mount_for(planned.path)
    if mount is not None:
        entry["mount"] = mount.path
    return entry


def _account(profile: Profile) -> dict[str, Any]:
    account = profile.service_account
    entry: dict[str, Any] = {
        "name": account.name,
        "shell": account.shell,
        "create": account.create_if_missing,
    }
    if account.group is not None:
        entry["group"] = account.group
    return entry


def summarize(plan: Mapping[str, Any]) -> str:
    """A short confirmation of what was produced, for a terminal.

    Deliberately short. The rendering that lays out every value beside the rule that
    produced it is the reporter's, and writing half of it here would mean writing it twice.

    The moment the plan was written is not printed. It is in the artifact, and leaving it
    out here means two runs that decided the same thing print the same thing -- which is
    what lets this output be captured into the documentation and checked byte for byte.
    """
    request = plan["request"]
    counts = plan["preflight"]["summary"]
    lines = [
        f"PLAN  {request['host']} -- {request['engine']} {request['version']}, "
        f"instance {request['instance']}",
        f"  plan id {plan['plan_id']}",
        "",
        f"  preflight     {counts['pass']} pass -- {counts['warn']} warn -- "
        f"{counts['block']} block -- {counts['skip']} skipped",
        f"  parameters    {len(plan['parameters'])}",
        f"  layout        {len(plan['layout']['paths'])} paths",
        f"  changes       {len(plan['changes'])}",
        f"  secrets       {len(plan['secrets'])}",
        "",
    ]

    warnings = plan["result"]["warnings"]
    if warnings:
        lines.append(
            f"RESULT  plan is applicable -- {warnings} "
            f"{'warning requires' if warnings == 1 else 'warnings require'} acknowledgement"
        )
    else:
        lines.append("RESULT  plan is applicable")
    lines.append("Nothing on the host was changed. Run with --json for the artifact itself.")
    return "\n".join(lines)
