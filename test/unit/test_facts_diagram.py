"""The picture of a host has to describe the host the code models.

Same guard as the profile anatomy diagram, for the same reason: a diagram is the part of
the documentation nobody rereads when the code changes. The renderer holds one list of
what a host is described by and the model holds another, and if they ever disagree the
build says so rather than the README quietly describing facts nothing collects.
"""

from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

from basewright.facts import HostFacts

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from render_assets import FACTS_MODEL  # noqa: E402


def test_the_diagram_lists_what_a_host_is_described_by() -> None:
    drawn = tuple(name for name, _, _ in FACTS_MODEL)
    modelled = tuple(field.name for field in fields(HostFacts))

    assert drawn == modelled, (
        "The fact model diagram in tools/render_assets.py lists different facts than "
        "HostFacts carries, or lists them in a different order. One of the two is out of "
        "date, and the picture is the one a reader will believe."
    )


def test_every_fact_says_what_reads_it() -> None:
    """A fact nothing consults is a fact that rots, so the diagram has to name a reader."""
    for name, carries, reader in FACTS_MODEL:
        assert carries, f"{name} is drawn without saying what it carries"
        assert reader, f"{name} is drawn without saying what reads it"


def test_the_diagram_names_no_engine() -> None:
    """The model describes machines. An engine named here would mean it had learned to
    expect one kind of host over another."""
    drawn = " ".join(part for row in FACTS_MODEL for part in row).lower()

    for engine in ("postgres", "mysql", "mariadb", "oracle", "sqlserver", "mssql"):
        assert engine not in drawn
