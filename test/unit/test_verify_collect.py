"""Assembling an observation document, and reading a socket table.

The two questions an engine's role is allowed to ask the core while it is reading an
instance. Neither knows an engine; the role calling them does. Both are here rather than in
a template because both have a wrong answer, and a wrong answer in a template is one nobody
finds until a container produces it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from basewright import __version__
from basewright.bridge import FILTERS
from basewright.verify.collect import observation, sockets_held
from basewright.verify.model import read_observation

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "test" / "fixtures" / "plan" / "applied.json"
OBSERVED = ROOT / "test" / "fixtures" / "observations" / "observed.json"


@pytest.fixture(scope="module")
def plan() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(PLAN.read_text(encoding="utf-8"))
    return document


@pytest.fixture(scope="module")
def sections() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(OBSERVED.read_text(encoding="utf-8"))
    read: dict[str, Any] = document["observations"]
    return read


# ------------------------------------------------------------------------ the envelope


def test_the_document_names_the_plan_and_the_host_it_was_read_on(
    plan: dict[str, Any], sections: dict[str, Any]
) -> None:
    """Both are read out of the plan rather than passed separately, so the two documents
    cannot disagree about which instance they are about."""
    written = observation(sections, plan, "2026-09-04T14:21:07Z")

    assert written["plan_id"] == plan["plan_id"]
    assert written["host"] == plan["request"]["host"]
    assert written["tool_version"] == __version__


def test_what_it_writes_is_a_document_the_core_will_read_back(
    plan: dict[str, Any], sections: dict[str, Any]
) -> None:
    """The whole point of assembling it here. A template building this field by field would
    be a second implementation of the contract, living where no test can reach it."""
    written = observation(sections, plan, "2026-09-04T14:21:07Z")

    assert read_observation(written, OBSERVED).plan_id == plan["plan_id"]


def test_a_section_nobody_could_read_is_left_out_rather_than_written_empty(
    plan: dict[str, Any], sections: dict[str, Any]
) -> None:
    """The difference the whole contract rests on. A role that wrote an empty reading for a
    question it could not put would turn a run that proved nothing into one that proved
    something false."""
    written = observation({**sections, "connection": {}}, plan, "2026-09-04T14:21:07Z")

    assert "connection" not in written["observations"]
    assert "service" in written["observations"]


@pytest.mark.parametrize(
    "given",
    [
        "2026-09-04T14:21:07Z",
        "2026-09-04T14:21:07",
        "2026-09-04T14:21:07.481Z",
        "2026-09-04T14:21:07+00:00",
    ],
)
def test_a_moment_is_written_to_the_second_however_it_arrived(
    given: str, plan: dict[str, Any], sections: dict[str, Any]
) -> None:
    """Trimmed here rather than in the template, so a role handing over a moment in a
    slightly different notation still writes a document the core can read."""
    written = observation(sections, plan, given)

    assert written["observed_at"] == "2026-09-04T14:21:07Z"


# -------------------------------------------------------------------- the socket table

#: One real `ss -H -ltnp` table, with the instance, something else, and a line that is not
#: a socket at all. The fourth field is the local address and port.
SS_OUTPUT = """\
LISTEN 0      244        127.0.0.1:5432       0.0.0.0:*    users:(("postgres",pid=812,fd=6))
LISTEN 0      244            [::1]:5432          [::]:*    users:(("postgres",pid=812,fd=5))
LISTEN 0      4096         0.0.0.0:22          0.0.0.0:*    users:(("sshd",pid=311,fd=3))
LISTEN 0      511                *:8080              *:*    users:(("nginx",pid=402,fd=8))
LISTEN 0      128           /run/db.sock                *    users:(("postgres",pid=812,fd=9))
something that is not a socket
"""


def test_only_the_sockets_the_named_process_holds_are_reported() -> None:
    """Not every socket on the host. What another service listens on is that service's
    business, and a conflict on the planned port is a gate that ran before this instance
    existed."""
    assert sockets_held(SS_OUTPUT, "postgres") == [
        {"address": "127.0.0.1", "port": 5432},
        {"address": "::1", "port": 5432},
    ]


def test_a_wildcard_address_is_written_the_way_a_person_would_type_it() -> None:
    assert sockets_held(SS_OUTPUT, "nginx") == [{"address": "0.0.0.0", "port": 8080}]


def test_an_ipv6_address_loses_the_brackets_that_belong_to_the_notation() -> None:
    held = sockets_held(SS_OUTPUT, "postgres")

    assert {"address": "::1", "port": 5432} in held


def test_a_process_holding_nothing_reports_nothing() -> None:
    """Which the port kind reads as an instance listening on nothing at all, and refuses."""
    assert sockets_held(SS_OUTPUT, "mariadbd") == []


def test_output_that_is_not_a_socket_table_is_not_guessed_at() -> None:
    assert sockets_held("", "postgres") == []
    assert sockets_held("no permission to see the process table\n", "postgres") == []


def test_a_socket_that_is_not_a_port_is_not_reported_as_one() -> None:
    """The instance holds a unix socket as well, and the fourth field is a path rather than
    an address and a port. Reporting it as port 0, or as whatever is after the last colon
    in a path, is the shape of wrong this parser is here to avoid."""
    held = sockets_held(SS_OUTPUT, "postgres")

    assert all(socket["port"] == 5432 for socket in held)
    assert len(held) == 2


def test_a_socket_with_no_holder_is_not_attributed_to_anyone() -> None:
    """`ss` reports the process only when the collector could see the process table. A
    socket with no name on it belongs to nobody as far as this is concerned."""
    without = "LISTEN 0 244 127.0.0.1:5432 0.0.0.0:*\n"

    assert sockets_held(without, "postgres") == []


# ------------------------------------------------------------------------- the bridge


def test_both_questions_are_reachable_from_ansible_and_nothing_else_is() -> None:
    """A filter is a question somebody decided a role may ask. Anything not here is a
    judgement a role would be making on its own."""
    assert FILTERS["basewright_observation"] is observation
    assert FILTERS["basewright_sockets"] is sockets_held
    assert set(FILTERS) == {
        "basewright_document",
        "basewright_repositories",
        "basewright_drift",
        "basewright_template",
        "basewright_observation",
        "basewright_sockets",
    }
