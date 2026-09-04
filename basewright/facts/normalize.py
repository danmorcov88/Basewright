"""Turning a collected facts document into the model the rules read.

Three passes, the same three a profile goes through, and for the same reason: a collector
author fixing one problem per run is a collector author having a bad afternoon.

1. **Canonicalize.** Casing, whitespace, and the two spellings of an architecture. This
   happens before validation, so the contract can stay strict about what the core consumes
   without demanding that a collector know which spelling this project prefers.
2. **Validate.** Against the closed schema, so an unknown key is an error rather than a
   fact silently ignored on the way to a plan.
3. **Reconcile.** The things a schema cannot say: that a mount cannot have more free space
   than it has, that two filesystems cannot be mounted at the same place, that a machine
   cannot have fewer threads than cores.

The third pass is worth the code. A host that contradicts itself is a collector that is
wrong somewhere, and every number it produced is then in question -- including the ones a
plan would be sized against.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from basewright.facts.errors import InvalidFactsError, MissingFactsError
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
from basewright.report.problems import Problem
from basewright.schema import problems_in
from basewright.units import render_bytes

Document = dict[str, Any]

FACTS_SCHEMA = "facts.schema.json"

#: The one spelling of each machine that reaches a rule. A collector reporting the other
#: one is not wrong, it is just reporting what its own tools call it.
ARCHITECTURES: dict[str, str] = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
    "ppc64le": "ppc64le",
    "s390x": "s390x",
}

#: Fields that are lowercased on the way in. Every one of them is compared against
#: something a profile wrote, and a comparison that fails on capitalisation is a
#: comparison that fails at three in the morning.
_LOWERCASED: tuple[tuple[str, ...], ...] = (
    ("os", "family"),
    ("os", "distro"),
    ("os", "codename"),
    ("arch",),
)


def load_facts(path: Path) -> HostFacts:
    """Read a facts document from disk and normalize it."""
    if not path.is_file():
        raise MissingFactsError(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InvalidFactsError(
            path,
            [
                Problem(
                    file=path.name,
                    location="",
                    message="is not valid JSON",
                    hint=" ".join(str(error).split()),
                )
            ],
        ) from error
    return normalize(document, source=path)


def normalize(document: object, source: Path | None = None) -> HostFacts:
    """Canonicalize, validate and reconcile a facts document."""
    path = source or Path("facts.json")
    if not isinstance(document, dict):
        raise InvalidFactsError(
            path,
            [
                Problem(
                    file=path.name,
                    location="",
                    message=f"is {type(document).__name__}, not a mapping of keys to values",
                    hint="A facts document is a mapping at the top level.",
                )
            ],
        )

    canonical = _canonicalize(document)

    problems = problems_in(canonical, schema_name=FACTS_SCHEMA, file=path.name)
    if problems:
        raise InvalidFactsError(path, problems)

    problems = list(_reconcile(canonical, path.name))
    if problems:
        raise InvalidFactsError(path, problems)

    return _build(canonical)


# ------------------------------------------------------------------------- canonicalizing


def _canonicalize(document: Document) -> Document:
    """Fold away the differences that are spelling rather than substance."""
    canonical = json.loads(json.dumps(document))

    for path in _LOWERCASED:
        _fold(canonical, path)

    arch = canonical.get("arch")
    if isinstance(arch, str):
        canonical["arch"] = ARCHITECTURES.get(arch, arch)

    return canonical  # type: ignore[no-any-return]


def _fold(document: Document, keys: tuple[str, ...]) -> None:
    """Lowercase and strip one field, if it is there and is a string."""
    target: Any = document
    for key in keys[:-1]:
        if not isinstance(target, dict):
            return
        target = target.get(key)
    if isinstance(target, dict):
        value = target.get(keys[-1])
        if isinstance(value, str):
            target[keys[-1]] = value.strip().lower()


# --------------------------------------------------------------------------- reconciling


def _reconcile(document: Document, file: str) -> Iterator[Problem]:
    """What a schema cannot say: that these numbers have to be true together."""
    yield from _mounts_are_possible(document, file)
    yield from _mounts_are_distinct(document, file)
    yield from _memory_is_possible(document, file)
    yield from _cores_and_threads_agree(document, file)


def _mounts_are_possible(document: Document, file: str) -> Iterator[Problem]:
    for index, mount in enumerate(document["mounts"]):
        if mount["free_bytes"] > mount["total_bytes"]:
            free = render_bytes(mount["free_bytes"])
            total = render_bytes(mount["total_bytes"])
            yield Problem(
                file=file,
                location=f"mounts[{index}].free_bytes",
                message=f"is {free} on a filesystem of {total}",
                hint=(
                    "A mount cannot have more space free than it has. Something in the "
                    "collector is reading the wrong filesystem, and every number it "
                    "reported is now in question, including the ones a plan would be "
                    "sized against."
                ),
            )


def _mounts_are_distinct(document: Document, file: str) -> Iterator[Problem]:
    seen: dict[str, int] = {}
    for index, mount in enumerate(document["mounts"]):
        path = str(mount["path"])
        if path in seen:
            yield Problem(
                file=file,
                location=f"mounts[{index}].path",
                message=f"is {path!r}, which mounts[{seen[path]}] also reports",
                hint=(
                    "Which filesystem carries a path is decided by matching the longest "
                    "one, and two answers at the same depth make that arbitrary. Report "
                    "the mount that is actually there."
                ),
            )
            continue
        seen[path] = index


def _memory_is_possible(document: Document, file: str) -> Iterator[Problem]:
    memory = document["memory"]
    available = memory.get("available_bytes")
    if available is not None and available > memory["total_bytes"]:
        yield Problem(
            file=file,
            location="memory.available_bytes",
            message=(
                f"is {render_bytes(available)} on a machine with "
                f"{render_bytes(memory['total_bytes'])} installed"
            ),
            hint="A host cannot have more memory available than it has.",
        )


def _cores_and_threads_agree(document: Document, file: str) -> Iterator[Problem]:
    cpu = document["cpu"]
    threads = cpu.get("threads")
    if threads is not None and threads < cpu["cores"]:
        yield Problem(
            file=file,
            location="cpu.threads",
            message=f"is {threads} on a processor reporting {cpu['cores']} cores",
            hint=(
                "A core runs at least one thread. Reporting fewer threads than cores "
                "usually means the two fields were filled in the wrong order, and sizing "
                "that divides by either of them will be wrong."
            ),
        )


# ------------------------------------------------------------------------------ building


def _build(document: Document) -> HostFacts:
    """Turn a validated document into the model. No decisions are taken here."""
    os_facts = document["os"]
    network = document["network"]

    return HostFacts(
        host=document["host"],
        collected_at=datetime.strptime(document["collected_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        ),
        os=OperatingSystem(
            family=os_facts["family"],
            distro=os_facts["distro"],
            version=os_facts["version"],
            codename=os_facts.get("codename"),
            pretty_name=os_facts.get("pretty_name"),
            kernel=os_facts.get("kernel"),
        ),
        arch=document["arch"],
        cpu=Cpu(
            cores=document["cpu"]["cores"],
            threads=document["cpu"].get("threads"),
            model=document["cpu"].get("model"),
        ),
        memory=Memory(
            total_bytes=document["memory"]["total_bytes"],
            available_bytes=document["memory"].get("available_bytes"),
            swap_bytes=document["memory"].get("swap_bytes"),
        ),
        mounts=tuple(_mount(entry) for entry in document["mounts"]),
        listening_ports=tuple(_listening(entry) for entry in network["listening_ports"]),
        services=tuple(_service(entry) for entry in document["services"]),
        locales=tuple(document["locales"]),
        reachable_repositories=_reachable_repositories(document.get("reachable_repositories")),
        privileges=Privileges(
            user=document["privileges"]["user"],
            can_escalate=bool(document["privileges"]["can_escalate"]),
        ),
        time_sync=_time_sync(document.get("time_sync")),
        kernel=_kernel(document.get("kernel")),
        firewall=_firewall(document.get("firewall")),
    )


def _reachable_repositories(entries: list[str] | None) -> tuple[str, ...] | None:
    """Which repositories answered, or None if nobody asked.

    The two are not the same answer and must not collapse into one: an empty list is a
    host that was asked and reached nothing, which refuses; None is a host that was never
    asked, which is unanswered.
    """
    return None if entries is None else tuple(entries)


def _mount(entry: Document) -> Mount:
    return Mount(
        path=entry["path"],
        filesystem=entry["filesystem"],
        total_bytes=entry["total_bytes"],
        free_bytes=entry["free_bytes"],
        device=entry.get("device"),
        rotational=entry.get("rotational"),
        options=tuple(entry.get("options", ())),
    )


def _listening(entry: Document) -> ListeningPort:
    return ListeningPort(
        port=entry["port"],
        address=entry["address"],
        protocol=entry["protocol"],
        process=entry.get("process"),
    )


def _service(entry: Document) -> InstalledService:
    return InstalledService(
        name=entry["name"],
        state=entry["state"],
        version=entry.get("version"),
        ports=tuple(entry.get("ports", ())),
    )


def _time_sync(entry: Document | None) -> TimeSync | None:
    if entry is None:
        return None
    return TimeSync(service=entry["service"], synchronized=bool(entry["synchronized"]))


def _kernel(entry: Document | None) -> KernelSettings | None:
    if entry is None:
        return None
    return KernelSettings(
        swappiness=entry.get("swappiness"),
        transparent_hugepages=entry.get("transparent_hugepages"),
        overcommit_memory=entry.get("overcommit_memory"),
    )


def _firewall(entry: Document | None) -> Firewall | None:
    if entry is None:
        return None
    return Firewall(
        service=entry["service"],
        active=bool(entry["active"]),
        open_ports=tuple(entry.get("open_ports", ())),
    )
