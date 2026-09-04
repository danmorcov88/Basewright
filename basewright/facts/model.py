"""The typed view of a host that every gate and the planner read.

This is not everything a machine could be asked about. It is what the rules need in order
to reach a verdict, and nothing else: every field here exists because some named rule
consults it. A fact nothing gates on is a fact that rots quietly, because nothing fails
when it stops being collected correctly.

The questions a rule actually asks are methods rather than field access. "Which mount
carries this path" has exactly one right answer and several plausible wrong ones, so it is
answered here, once, and the gate that checks free space and the plan that reports the
mount cannot disagree about it.

Everything is frozen. Facts are what was true when they were collected; a run that adjusts
them as it goes is a run whose plan no longer describes anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from basewright.units import render_bytes


def path_components(path: str) -> tuple[str, ...]:
    """Split a path into the parts a prefix comparison can be made on.

    Comparing paths as strings makes ``/var`` a prefix of ``/variable``, which is how a
    threshold ends up being checked against the wrong filesystem. Comparing components
    does not.
    """
    return tuple(part for part in path.replace("\\", "/").split("/") if part)


@dataclass(frozen=True)
class OperatingSystem:
    """What the host runs, as the collector reported it.

    ``family`` is observed, never derived. Working out that one distribution is packaged
    like another is knowledge about operating systems, and it belongs where the
    observation is made rather than in the code that reads the answer.
    """

    family: str
    distro: str
    version: str
    codename: str | None = None
    pretty_name: str | None = None
    kernel: str | None = None

    @property
    def major(self) -> str:
        """The leading component of the version.

        Repositories are keyed by it on the families that do not use a code name, and a
        support matrix lists it where a distribution promises compatibility across the
        minor releases. Splitting it here means the two cannot disagree about whether
        ``9.4`` is nine.
        """
        return self.version.split(".", 1)[0]

    def __str__(self) -> str:
        return self.pretty_name or f"{self.distro} {self.version}"


@dataclass(frozen=True)
class Cpu:
    cores: int
    threads: int | None = None
    model: str | None = None


@dataclass(frozen=True)
class Memory:
    total_bytes: int
    available_bytes: int | None = None
    swap_bytes: int | None = None

    def __str__(self) -> str:
        return render_bytes(self.total_bytes)


@dataclass(frozen=True)
class Mount:
    """One mounted filesystem."""

    path: str
    filesystem: str
    total_bytes: int
    free_bytes: int
    device: str | None = None
    rotational: bool | None = None
    options: tuple[str, ...] = ()

    @property
    def read_only(self) -> bool:
        """A planned path on a read-only mount is a refusal, not a surprise at apply time."""
        return "ro" in self.options

    @property
    def components(self) -> tuple[str, ...]:
        return path_components(self.path)

    def carries(self, path: str) -> bool:
        """Whether this filesystem is the one a path lives on, or an ancestor of it."""
        mine = self.components
        return path_components(path)[: len(mine)] == mine

    def __str__(self) -> str:
        kind = (
            "unknown" if self.rotational is None else ("rotational" if self.rotational else "SSD")
        )
        return f"{self.path}  {render_bytes(self.free_bytes)} free, {self.filesystem}, {kind}"


@dataclass(frozen=True)
class ListeningPort:
    port: int
    address: str
    protocol: str
    process: str | None = None


@dataclass(frozen=True)
class InstalledService:
    """Something already installed on the host.

    Whether it conflicts with what is being provisioned is a question the profile answers.
    The core reads a name and compares it to what a profile declared; it recognises
    nothing on its own.
    """

    name: str
    state: str
    version: str | None = None
    ports: tuple[int, ...] = ()


@dataclass(frozen=True)
class TimeSync:
    service: str
    synchronized: bool


@dataclass(frozen=True)
class KernelSettings:
    swappiness: int | None = None
    transparent_hugepages: str | None = None
    overcommit_memory: int | None = None


@dataclass(frozen=True)
class Firewall:
    service: str
    active: bool
    open_ports: tuple[int, ...] = ()

    def admits(self, port: int) -> bool:
        return not self.active or port in self.open_ports


@dataclass(frozen=True)
class Privileges:
    user: str
    can_escalate: bool


@dataclass(frozen=True)
class HostFacts:
    """One host, as the rules see it."""

    host: str
    collected_at: datetime
    os: OperatingSystem
    arch: str
    cpu: Cpu
    memory: Memory
    mounts: tuple[Mount, ...]
    listening_ports: tuple[ListeningPort, ...]
    services: tuple[InstalledService, ...]
    locales: tuple[str, ...]
    privileges: Privileges
    reachable_repositories: tuple[str, ...] | None = None
    time_sync: TimeSync | None = None
    kernel: KernelSettings | None = None
    firewall: Firewall | None = None

    # ------------------------------------------------------------------ questions

    def mount_for(self, path: str) -> Mount | None:
        """The filesystem a path lives on: the deepest mount that is a prefix of it.

        Returns None only when the host reports no mount covering the path at all, which
        on a complete set of facts means the path is not on this machine.
        """
        candidates = [mount for mount in self.mounts if mount.carries(path)]
        if not candidates:
            return None
        return max(candidates, key=lambda mount: len(mount.components))

    def free_bytes_for(self, path: str) -> int | None:
        mount = self.mount_for(path)
        return None if mount is None else mount.free_bytes

    def shares_mount_with(self, path: str, other: str) -> bool:
        """Whether two paths compete for the same spindle, queue and free space."""
        mine = self.mount_for(path)
        theirs = self.mount_for(other)
        return mine is not None and theirs is not None and mine.path == theirs.path

    def port_in_use(self, port: int, protocol: str = "tcp") -> ListeningPort | None:
        return next(
            (
                listening
                for listening in self.listening_ports
                if listening.port == port and listening.protocol == protocol
            ),
            None,
        )

    def locale_present(self, locale: str) -> bool:
        return locale in self.locales

    def service_named(self, name: str) -> InstalledService | None:
        return next((service for service in self.services if service.name == name), None)

    def can_reach(self, url: str) -> bool | None:
        """Whether the host proved it can reach one package repository.

        None means the question was never put to the machine, which is a different answer
        from no and is reported differently. Nothing else in this model is three-valued,
        and this is the one fact whose collection depends on knowing what is being
        provisioned.
        """
        if self.reachable_repositories is None:
            return None
        return url in self.reachable_repositories

    # -------------------------------------------------------------------- rendering

    def plan_section(self) -> dict[str, Any]:
        """The host as a plan carries it.

        A plan records what the machine was when the decisions were made, so that a value
        can be argued about later. It is a subset: ports and installed services matter to
        the gates and say nothing about why a parameter is the size it is.
        """
        section: dict[str, Any] = {
            "os": _without_none(
                {
                    "family": self.os.family,
                    "distro": self.os.distro,
                    "version": self.os.version,
                    "pretty_name": self.os.pretty_name,
                    "kernel": self.os.kernel,
                }
            ),
            "arch": self.arch,
            "cpu": _without_none({"cores": self.cpu.cores, "model": self.cpu.model}),
            "memory": _without_none(
                {"total_bytes": self.memory.total_bytes, "swap_bytes": self.memory.swap_bytes}
            ),
            "storage": [
                _without_none(
                    {
                        "mount": mount.path,
                        "free_bytes": mount.free_bytes,
                        "total_bytes": mount.total_bytes,
                        "filesystem": mount.filesystem,
                        "rotational": mount.rotational,
                    }
                )
                for mount in self.mounts
            ],
        }
        if self.time_sync is not None:
            section["time_sync"] = {
                "service": self.time_sync.service,
                "synchronized": self.time_sync.synchronized,
            }
        return section


def _without_none(values: dict[str, Any]) -> dict[str, Any]:
    """Drop the keys nothing was observed for.

    The plan schema is closed and its optional fields are optional, so an unobserved fact
    is absent rather than present and null. Null would claim the question was asked and
    answered with nothing.
    """
    return {key: value for key, value in values.items() if value is not None}
