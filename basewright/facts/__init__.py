"""Normalization of raw host facts into a typed, engine-agnostic model.

Raw facts arrive in whatever shape the collector produced them. Everything downstream
reads the normalized model instead, so a change in a collector cannot ripple into the gate
engine or the planner.

The model carries what the rules need in order to reach a verdict and nothing else. A fact
no rule consults is a fact that rots quietly, because nothing fails when it stops being
collected correctly.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from basewright.facts.collect import document
from basewright.facts.errors import FactsError, InvalidFactsError, MissingFactsError
from basewright.facts.model import (
    Cpu,
    Firewall,
    HostFacts,
    InstalledService,
    KernelSettings,
    ListeningPort,
    Memory,
    Mount,
    OperatingSystem,
    Privileges,
    TimeSync,
)
from basewright.facts.normalize import ARCHITECTURES, FACTS_SCHEMA, load_facts, normalize
from basewright.facts.repositories import repositories

#: The filters the collecting role reaches this package through, and the whole of what
#: Ansible is allowed to call. There are two because the role asks two questions -- what
#: did this host turn out to be, and which repositories should it be asked about -- and
#: both answers are decided here rather than assembled in a template. The role's template
#: is still one line long, which is the point of the arrangement rather than an accident:
#: the boundary between the half that acts and the half that decides is not a place to
#: leave a second implementation of anything.
FILTERS: Mapping[str, Callable[..., object]] = {
    "basewright_document": document,
    "basewright_repositories": repositories,
}

__all__ = [
    "ARCHITECTURES",
    "FACTS_SCHEMA",
    "FILTERS",
    "Cpu",
    "FactsError",
    "Firewall",
    "HostFacts",
    "InstalledService",
    "InvalidFactsError",
    "KernelSettings",
    "ListeningPort",
    "Memory",
    "MissingFactsError",
    "Mount",
    "OperatingSystem",
    "Privileges",
    "TimeSync",
    "document",
    "load_facts",
    "normalize",
    "repositories",
]
