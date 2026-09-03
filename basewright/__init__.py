"""Basewright: automated provisioning of database instances on servers that already exist.

This package is the part of Basewright that *decides*. It normalizes host facts,
evaluates preflight gates, sizes parameters from declarative rules, and assembles a
plan. It performs no remote change; applying a plan is Ansible's job.

Nothing in this package knows the name of any database engine. Engine-specific
knowledge lives in ``profiles/`` as data and reaches the core only through the
profile schema.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
