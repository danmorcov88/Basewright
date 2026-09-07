"""Assembling an observation document out of what a role read.

The counterpart of :mod:`basewright.facts.collect`, and here for the same reason: a
template that built a contract document field by field would be a second implementation of
that contract, living where no test can reach it. An engine's role reads its instance and
hands over a mapping per kind; this puts the envelope round it, and the role's template is
one line long.

Nothing here knows an engine. The sections arrive already in the contract's terms, because
turning what a particular server said into those terms is the one part of observing that
needs to know which server it was -- and that part is the role's.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from basewright import __version__
from basewright.verify.model import OBSERVATION_SCHEMA  # noqa: F401 - re-exported for callers

#: The version of the contract in ``schema/observation.schema.json``.
SCHEMA_VERSION = "1"

#: An ``ss`` line names its holders as a list, and the first name is the process.
_HOLDER = re.compile(r'users:\(\("([^"]+)"')

#: ``ss -H -ltnp`` writes the local address and port in the fourth field, counting from
#: one. Fewer fields than this is a line that is not a socket.
_SS_FIELDS = 6


def observation(
    sections: Mapping[str, Mapping[str, Any]],
    plan: Mapping[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    """The whole observation document, from what a role managed to read.

    A section whose value is empty is dropped rather than written. That is the difference
    the contract rests on: a kind absent from the document is one nobody managed to
    observe, and a role that wrote an empty reading for a question it could not put would
    turn a run that proved nothing into a run that proved something false.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan["plan_id"],
        "host": plan["request"]["host"],
        "observed_at": _to_the_second(observed_at),
        "tool_version": __version__,
        "observations": {kind: dict(value) for kind, value in sections.items() if value},
    }


def sockets_held(output: str, process: str) -> list[dict[str, Any]]:
    """Which sockets one process is listening on, from ``ss -H -ltnp``.

    The process name is the caller's, because only the role knows what its own instance
    calls itself. What is done with the answer -- reading a port out of a field that holds
    an address and a port, and knowing that ``*`` is how ss writes every address -- is the
    same for every engine, and is the part that has a wrong answer.
    """
    found: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < _SS_FIELDS:
            continue

        holder = _HOLDER.search(line)
        if holder is None or holder.group(1) != process:
            continue

        address, _, port = fields[3].rpartition(":")
        if not port.isdigit():
            continue

        found.append(
            {
                "port": int(port),
                # ``*`` is how ss writes "every address", and the contract prefers the
                # form a person would type. An IPv6 address arrives bracketed, and the
                # brackets belong to the notation rather than to the address.
                "address": "0.0.0.0" if address in {"*", ""} else address.strip("[]"),
            }
        )

    return sorted(found, key=lambda socket: (socket["port"], socket["address"]))


def _to_the_second(moment: str) -> str:
    """A moment as the contract spells it, from whatever Ansible handed over.

    ``ansible_date_time.iso8601`` is already this, and a sub-second or offset spelling is
    not. Trimming here rather than in the template means a role that hands over a moment
    in a slightly different notation is still writing a document the core can read.
    """
    text = moment.strip()
    if text.endswith("Z"):
        text = text[:-1]
    return f"{text.split('.')[0].split('+')[0][:19]}Z"
