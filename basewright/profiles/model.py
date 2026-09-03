"""The typed view of a profile that the rest of the core reads.

Schema validation proves a profile is well formed. These types are what makes it
convenient to use afterwards: the gate engine asks for rules, the planner asks for sizing
rules and paths, the reporter asks for versions and package names, and none of them parses
YAML or knows which file a value came from.

Everything here is frozen. A profile is read once and then it is a fact about the run, not
a thing that gets adjusted as the run proceeds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class SupportedOS:
    """One operating system a version may be installed on."""

    family: str
    distro: str
    versions: tuple[str, ...]


@dataclass(frozen=True)
class SupportedVersion:
    """One engine version, and the ground it is supported on."""

    version: str
    eol: date
    status: str
    arch: tuple[str, ...]
    supported_os: tuple[SupportedOS, ...]

    def supports(self, *, distro: str, version: str, arch: str) -> bool:
        """Whether this engine version may be installed on the described host."""
        if arch not in self.arch:
            return False
        return any(
            entry.distro == distro and version in entry.versions for entry in self.supported_os
        )


@dataclass(frozen=True)
class GateRule:
    """A preflight rule contributed by the profile.

    There are two severities. There is no flag anywhere that turns a block into a warning:
    if a block is wrong, the rule is wrong, and the rule is fixed where a reviewer sees it.
    """

    identifier: str
    severity: str
    title: str
    expr: str
    remediation: str
    applies_to: str | None = None

    @property
    def blocking(self) -> bool:
        return self.severity == "block"


@dataclass(frozen=True)
class SizingRule:
    """A parameter, how it is derived, and why it is derived that way.

    ``why`` is not decoration. It is rendered into the plan beside the value, which is what
    makes a plan reviewable six months after the person who ran it has moved on.
    """

    identifier: str
    parameter: str
    expr: str
    why: str
    unit: str = "count"
    minimum: str | float | None = None
    maximum: str | float | None = None
    warn_above: str | float | None = None
    round_to: str | float | None = None


@dataclass(frozen=True)
class PathSpec:
    """Where one kind of file lives, and what the mount carrying it must have free."""

    purpose: str
    default: str
    mode: str
    min_free: str | None = None
    description: str = ""


@dataclass(frozen=True)
class ServiceAccount:
    """The account the instance runs as."""

    name: str
    create_if_missing: bool
    shell: str
    group: str | None = None
    home: str | None = None


@dataclass(frozen=True)
class Repository:
    """A vendor package repository. Never a source build, never a tarball."""

    name: str
    url: str
    key_url: str | None = None
    suite: str | None = None
    components: tuple[str, ...] = ()
    gpg_check: bool = True


@dataclass(frozen=True)
class PackageSet:
    """What to install on one operating system family, and what service results."""

    family: str
    packages: tuple[str, ...]
    service: str
    repository: Repository | None = None


@dataclass(frozen=True)
class VerifyCheck:
    """One assertion about the running instance."""

    identifier: str
    kind: str
    title: str
    remediation: str
    expr: str | None = None


@dataclass(frozen=True)
class Profile:
    """One engine, as data. The only shape in which the core ever meets an engine."""

    root: Path
    engine: str
    display_name: str
    profile_version: str
    summary: str
    os_families: tuple[str, ...]
    default_port: int
    default_instance: str
    default_version: str
    versions: tuple[SupportedVersion, ...]
    gates: tuple[GateRule, ...]
    paths: Mapping[str, PathSpec]
    service_account: ServiceAccount
    sizing: tuple[SizingRule, ...]
    packages: Mapping[str, PackageSet]
    checks: tuple[VerifyCheck, ...]
    documentation: str | None = None

    def version(self, version: str) -> SupportedVersion | None:
        """The support matrix entry for one version, or None if it is not listed."""
        return next((entry for entry in self.versions if entry.version == version), None)

    def path(self, purpose: str) -> PathSpec | None:
        """The layout entry for one purpose, or None if the profile does not define it."""
        return self.paths.get(purpose)

    def packages_for(self, family: str) -> PackageSet | None:
        """What to install on one operating system family."""
        return self.packages.get(family)

    @property
    def templates(self) -> Path:
        """Where the profile keeps its configuration templates."""
        return self.root / "templates"
