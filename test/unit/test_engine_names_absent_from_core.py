"""The core must never learn the name of a database engine.

This is the rule the whole architecture rests on: engines are data, not code.
The moment a conditional in the core branches on an engine name, adding an engine
stops being a matter of writing a profile and becomes a matter of editing the
planner -- which is the failure mode this project exists to avoid.

The check is deliberately blunt. It scans every source line of the core, including
comments and docstrings, because an example in a docstring is how the first
engine name usually gets in.
"""

from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "basewright"

#: Names that must not appear anywhere in the core, in any casing.
ENGINE_NAMES: tuple[str, ...] = (
    "cassandra",
    "clickhouse",
    "cockroach",
    "mariadb",
    "mongodb",
    "mssql",
    "mysql",
    "oracle",
    "pgsql",
    "postgres",
    "postgresql",
    "redis",
    "sqlserver",
    "sqlite",
)

#: Files exempt from the rule, with the reason. Empty, and meant to stay that way:
#: an entry here is an admission that the profile schema is missing something.
EXEMPT: dict[str, str] = {}

_PATTERN = re.compile(r"\b(" + "|".join(ENGINE_NAMES) + r")\b", re.IGNORECASE)


def _core_sources() -> list[Path]:
    return sorted(p for p in CORE.rglob("*.py") if p.name not in EXEMPT)


def test_core_has_sources_to_check() -> None:
    """A guard that scans nothing is a guard that always passes."""
    assert _core_sources(), f"no Python sources found under {CORE}"


def test_no_engine_name_appears_in_the_core() -> None:
    offences: list[str] = []
    for source in _core_sources():
        for lineno, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            match = _PATTERN.search(line)
            if match:
                relative = source.relative_to(CORE.parent)
                offences.append(f"{relative}:{lineno}: {match.group(1)!r} in: {line.strip()}")

    assert not offences, (
        "The core branched on, or referred to, a database engine by name:\n  "
        + "\n  ".join(offences)
        + "\n\nEngine-specific knowledge belongs in profiles/. If the core genuinely needs "
        "this information, extend the profile schema so the profile can supply it."
    )
