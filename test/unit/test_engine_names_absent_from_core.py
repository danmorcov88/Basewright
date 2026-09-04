"""The core must never learn the name of a database engine.

This is the rule the whole architecture rests on: engines are data, not code.
The moment a conditional in the core branches on an engine name, adding an engine
stops being a matter of writing a profile and becomes a matter of editing the
planner -- which is the failure mode this project exists to avoid.

The check is deliberately blunt. It scans every source line of the core, including
comments and docstrings, because an example in a docstring is how the first
engine name usually gets in.

The schemas are scanned on the same terms. A schema is core knowledge -- it is the
vocabulary in which every engine is described -- so an engine named there would mean the
core had learned to expect one shape of engine over another, which is the same failure
wearing different clothes.

So are the shared Ansible roles, which the rule has always covered and nothing checked
until there was one. A role that runs for every engine is core logic that happens to be
written in YAML, and a collector that went looking for one service by name would be the
same defect as a planner that branched on one -- with the added problem that it would make
the fact document quietly incomplete for every engine it had not heard of. An engine's own
role, under ``ansible/roles/<engine>/``, is the place engine names are supposed to be, and
is not scanned.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "basewright"
SCHEMA = ROOT / "schema"
ROLES = ROOT / "ansible" / "roles"
PLUGINS = ROOT / "ansible" / "plugins"
PLAYBOOKS = ROOT / "ansible" / "playbooks"

#: The roles that run whatever is being provisioned. Every other directory under
#: ``ansible/roles/`` belongs to one engine and is where its name is meant to appear, so
#: this list is what gets scanned rather than what gets skipped: a role added here is a
#: decision, and a role that is not shared cannot be swept in by accident.
SHARED_ROLES: tuple[str, ...] = ("common", "gather")

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
    sources = [p for p in CORE.rglob("*.py") if p.name not in EXEMPT]
    sources.extend(p for p in SCHEMA.rglob("*.json") if p.name not in EXEMPT)
    sources.extend(_shared_role_sources())
    return sorted(sources)


def _shared_role_sources() -> list[Path]:
    """The half of the core that is written in YAML.

    Everything under a shared role counts: a task, a default, a template, the metadata.
    A template is the one worth naming, because it is where a name would arrive looking
    like configuration rather than like a conditional.
    """
    sources: list[Path] = []
    for role in SHARED_ROLES:
        directory = ROLES / role
        if not directory.exists():
            continue
        sources.extend(p for p in directory.rglob("*") if p.is_file() and p.name not in EXEMPT)
    sources.extend(p for p in PLUGINS.rglob("*.py") if p.name not in EXEMPT)
    sources.extend(p for p in PLAYBOOKS.rglob("*.yml") if p.name not in EXEMPT)
    return sources


def test_core_has_sources_to_check() -> None:
    """A guard that scans nothing is a guard that always passes."""
    assert _core_sources(), f"no sources found under {CORE} or {SCHEMA}"


def test_the_schema_is_scanned_too() -> None:
    """The schemas are the vocabulary the core describes every engine in."""
    assert any(source.suffix == ".json" for source in _core_sources())


def test_the_shared_roles_are_scanned_too() -> None:
    """The rule has always covered them. Nothing checked it until one existed."""
    scanned = {source.relative_to(ROOT).as_posix() for source in _core_sources()}
    assert "ansible/roles/gather/tasks/main.yml" in scanned
    assert "ansible/roles/gather/templates/facts.json.j2" in scanned
    assert "ansible/playbooks/gather.yml" in scanned


def test_an_engine_role_is_not_scanned() -> None:
    """Where an engine name belongs. A guard that forbade it everywhere would forbid
    engines, which is the opposite of the arrangement it exists to protect."""
    for role in SHARED_ROLES:
        assert (ROLES / role).exists(), f"{role} is listed as shared but does not exist"
    others = {p.name for p in ROLES.iterdir() if p.is_dir()} - set(SHARED_ROLES)
    scanned = {
        source.relative_to(ROOT).parts[2]
        for source in _shared_role_sources()
        if source.is_relative_to(ROLES)
    }
    assert not (others & scanned)


def test_no_engine_name_appears_in_the_core() -> None:
    offences: list[str] = []
    for source in _core_sources():
        for lineno, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            match = _PATTERN.search(line)
            if match:
                relative = source.relative_to(ROOT)
                offences.append(f"{relative}:{lineno}: {match.group(1)!r} in: {line.strip()}")

    assert not offences, (
        "The core branched on, or referred to, a database engine by name:\n  "
        + "\n  ".join(offences)
        + "\n\nEngine-specific knowledge belongs in profiles/. If the core genuinely needs "
        "this information, extend the profile schema so the profile can supply it."
    )
