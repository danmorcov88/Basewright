"""Ansible's way in to the functions that decide things.

A bridge and nothing else. Every line that could be wrong -- about what a machine printed,
about which repositories a profile installs from, about whether a host is still the one a
plan describes -- lives in ``basewright.bridge`` and the modules under it, where pytest
covers it against the output of real hosts. A parser or a comparison reachable only by
running a playbook against a container is one nobody tests the edges of.

This means the control node needs Basewright installed, which it does anyway: the
playbooks finish by running the CLI over the documents they have just read or written.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from basewright.bridge import FILTERS


class FilterModule:
    """The class name and method Ansible looks for. Neither is ours to choose."""

    def filters(self) -> dict[str, Callable[..., Any]]:
        return dict(FILTERS)
