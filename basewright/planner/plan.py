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

__all__ = [
    "SCHEMA_VERSION",
    "build_plan",
    "content_of",
    "plan_id_for",
    "rendered",
]

#: The two fields the digest is never taken over: the moment the plan was written, which
#: two identical decisions differ in, and the plan's own name, which cannot be part of
#: what produces it.
_OUTSIDE_THE_DIGEST = ("plan_id", "generated_at")

#: The version of the plan contract. Apply refuses a plan whose major version it does not
#: implement, rather than guessing at a field that moved.
#:
#: Two, since the contract gained an `initialization` section. The first version described
#: everything apply executes except creating the instance -- which is the one act on the
#: list that cannot be performed again differently, and which was therefore the worst
#: thing to have left implicit. A version rather than a patch, because a plan written
#: under the old contract does not carry it and apply must say so rather than default it.
SCHEMA_VERSION = "2"

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
        **({} if actions.initialization is None else {"initialization": actions.initialization}),
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


def content_of(plan: Mapping[str, Any]) -> dict[str, Any]:
    """A finished plan, reduced to the part its name is taken over.

    There is one definition of what a plan's content is, and it is here, so that the
    planner computing an id and a reader checking one cannot disagree about it.
    """
    return {key: value for key, value in plan.items() if key not in _OUTSIDE_THE_DIGEST}


def plan_id_for(content: Mapping[str, Any]) -> str:
    """The name a plan is known by: a digest of everything it says.

    ``content`` is the plan without its own name and without the moment it was written,
    and it has to arrive that way. Two runs that reached the same conclusions about the
    same host produce the same id, so a plan can be found again from the id printed in a
    task log, and a plan that differs from the one somebody approved says so in its name.
    """
    present = [field for field in _OUTSIDE_THE_DIGEST if field in content]
    if present:
        raise PlanError(
            f"The plan id is computed over the plan without {' and without '.join(present)}. "
            "Build the document without it, or reduce a finished plan with content_of: a "
            "digest taken over its own answer, or over the second two runs differ in, is "
            "not a name for what was decided."
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
