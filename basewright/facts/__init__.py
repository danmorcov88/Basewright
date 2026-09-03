"""Normalization of raw host facts into a typed, engine-agnostic model.

Raw facts arrive in whatever shape the collector produced them. Everything downstream
reads the normalized model instead, so a change in a collector cannot ripple into the gate
engine or the planner.

The model carries what the rules need in order to reach a verdict and nothing else. A fact
no rule consults is a fact that rots quietly, because nothing fails when it stops being
collected correctly.
"""

from __future__ import annotations

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

__all__ = [
    "ARCHITECTURES",
    "FACTS_SCHEMA",
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
    "load_facts",
    "normalize",
]
