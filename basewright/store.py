"""Where a plan lives between the person who produced it and the person who applies it.

§12 of the brief asks for plans in a durable location so that `Apply` can be run by somebody
other than whoever produced the plan, and calls that separation a feature rather than an
accident. It is the reason this exists: the Semaphore template for applying takes a **plan
id**, not a path, so the id printed in one task log has to be enough to find the artifact
from another task, another day, another person.

The store is two things and deliberately not a third.

**Plans, addressed by content.** ``plans/<plan_id>.json``, and a plan id is a digest of the
plan's own content (ADR-0017), so the name and the checksum are the same string. Writing a
plan that is already there is not an error and not an overwrite: it is the same bytes, and
saying so is cheaper than deciding what to do about a collision that cannot happen.

**One pointer per instance.** ``instances/<host>/<instance>`` holds the id of the plan last
applied there, so the Verify template can take the host and the instance name that §12 says
it takes rather than asking an operator to remember an id.

Reading that pointer is this module's job and writing it is not. ``apply`` asks where the
pointer for a plan goes -- a question with a wrong answer, since the parts of the path come
from a survey field somebody typed -- and then writes it itself, which is the split the
whole project is built on (ADR-0008). There is no second program here for a playbook to
call.

**It is not an audit trail.** The pointer is overwritten on every apply. There is no
history, no who and no when, because those are Phase E and building half of them here would
produce something that looks like a record and answers none of the questions a record is
asked. What this answers is exactly one question -- *which plan is this instance supposed to
match* -- and that is the question verify needs answered.

Nothing here is engine-specific and nothing here reads a profile. A plan is a document; this
puts documents somewhere and finds them again.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from basewright.report.problems import display

#: What a plan id looks like, and the whole of what may become a filename here. A path
#: separator or a dot-dot in an id would be a traversal, and an id arrives from a survey
#: field somebody typed, so it is checked rather than trusted.
_PLAN_ID = re.compile(r"^[a-z0-9-]{4,80}$")

#: What a host or an instance name may be, for the same reason. Deliberately narrower than
#: a hostname can be in general: what is being built is a directory name.
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

#: Where a store keeps each of its two halves.
PLANS = "plans"
INSTANCES = "instances"


class StoreError(Exception):
    """The store cannot answer, and the message says what to do about it.

    One class rather than a hierarchy: every caller here does the same thing with it, which
    is print it and exit. A store that is missing and a plan that is not in it are different
    sentences rather than different types.
    """


def plan_path(root: Path, plan_id: str) -> Path:
    """Where the plan with this id would be kept."""
    return root / PLANS / f"{_checked(plan_id, _PLAN_ID, 'plan id')}.json"


def instance_path(root: Path, host: str, instance: str) -> Path:
    """Where the pointer for one instance on one host would be kept."""
    return (
        root
        / INSTANCES
        / _checked(host, _NAME, "host name")
        / _checked(instance, _NAME, "instance name")
    )


def keep(root: Path, document: dict[str, Any], rendered: str) -> Path:
    """Put a plan in the store under its own id, and say where it went.

    ``rendered`` is the bytes the plan step produced rather than a fresh serialization of
    ``document``, because a plan is named after a digest of its content and the artifact
    that gets read later must be the one the digest was taken over -- not an equivalent one
    this function happened to write.

    Writing a plan that is already there is a no-op. The id is the digest, so the file that
    is there has the same content by construction.
    """
    destination = plan_path(root, document["plan_id"])
    if destination.exists():
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    _write(destination, rendered)
    return destination


def read(root: Path, plan_id: str) -> str:
    """The plan with this id, as it was written.

    Returns the text rather than a parsed document, so that whoever asked for it checks it
    against the contract the same way they would check a plan read from anywhere else. A
    store is a place to put files, not a second opinion about what is in them.
    """
    path = plan_path(root, plan_id)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise StoreError(_not_found(root, plan_id)) from error


def applied(root: Path, host: str, instance: str) -> str:
    """Which plan this instance is supposed to match, or a refusal saying nobody said."""
    path = instance_path(root, host, instance)
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise StoreError(
            f"the store at {display(root)} does not say which plan {host} is running "
            f"instance {instance} from. Either it was never applied through this store, or "
            f"it was applied through another one. Apply a plan to it, or name the plan id "
            f"directly."
        ) from error


def _not_found(root: Path, plan_id: str) -> str:
    """Why a plan is not there, with the closest thing to a next step there is.

    Naming a few ids that *are* there is the useful half: the failure this message is read
    after is almost always a typo or a store that is not the one the plan went into, and
    both look identical until somebody sees what the store does hold.
    """
    held = ", ".join(known(root)[:5]) or "it holds no plans at all"
    return (
        f"the store at {display(root)} has no plan {plan_id}. It holds: {held}. A plan id "
        f"is a digest of the plan's own content, so it is printed by the step that produced "
        f"the plan and does not have to be typed twice."
    )


def known(root: Path) -> list[str]:
    """Every plan id the store holds, oldest name first. Used to explain a miss."""
    directory = root / PLANS
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


def _checked(value: str, pattern: re.Pattern[str], what: str) -> str:
    """A value that is about to become part of a path, or a refusal naming it.

    Every one of these arrives from a survey field an operator typed into Semaphore, so the
    interesting input is not a wrong id but a `../` -- and the answer to that is to refuse
    the shape rather than to sanitize it into something else.
    """
    if not pattern.match(value or ""):
        raise StoreError(
            f"{value!r} is not a {what} this store can use. A {what} is letters, digits and "
            f"the punctuation in between; anything that could name a directory somewhere "
            f"else is refused rather than tidied into something it did not say."
        )
    return value


def _write(path: Path, text: str) -> None:
    """Write a file the store owns, readable by nobody who is not meant to read it.

    A plan is safe to share -- it names where a secret is and never what it is (ADR-0007) --
    so this is not protecting a credential. It is that a store somebody else can write to is
    a store whose plans somebody else can substitute, and the id would still match because
    they would have recomputed it.
    """
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o640)
