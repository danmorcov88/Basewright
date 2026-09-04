"""Ansible's way in to the collecting functions.

A bridge and nothing else. Every line that could be wrong about what a machine printed,
and every line that decides which repositories a host should be asked to reach, lives in
``basewright.facts``, where pytest covers it against the output of a real host; a parser
reachable only by running a playbook against a container is a parser nobody tests the
edges of.

This also means the control node needs Basewright installed, which it does anyway: the
playbook finishes by running the CLI over the document it just wrote.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from basewright.facts import FILTERS


class FilterModule:
    """The class name and method Ansible looks for. Neither is ours to choose."""

    def filters(self) -> dict[str, Callable[..., Any]]:
        return dict(FILTERS)
