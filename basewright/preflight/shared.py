"""The rules that apply to every engine.

These are the twenty in the brief. They are written in Python rather than as expressions
in a data file, and the reason is the refusal: a rule has to name the observed value *and*
the required one, per path where there is more than one path, and a boolean expression can
produce neither. "Refused because /backup has 2.0 GiB free and this profile requires
50 GB" is an answer somebody can act on; "refused because disk.free_space was false" sends
them back to the host to find out what it means.

None of that makes them engine-aware. Every threshold they compare against comes from the
profile -- the minimums, the preferences, the conflicts, the layout, the support matrix --
and where a profile states none, the rule reports ``skip`` rather than inventing one. What
is written here is the *question*, which is the same for every engine. The answer is
always data.

Each rule returns a verdict describing what it saw. What that costs is decided elsewhere,
by the severity written beside the rule, which is the only place severity is resolved.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from basewright.facts.model import HostFacts
from basewright.layout import PlannedPath
from basewright.preflight.model import Severity, Verdict
from basewright.profiles.model import Profile, SupportedVersion
from basewright.request import Request
from basewright.units import render_bytes

#: How close to the end of support is close enough to say so. Twelve months is the point
#: at which a version stops being a choice and becomes a migration that has to be planned,
#: and it is core policy rather than a profile's, because it is about how long it takes an
#: organisation to move rather than about any engine.
EOL_HORIZON = timedelta(days=365)


@dataclass(frozen=True)
class Context:
    """Everything the shared rules read, gathered once."""

    facts: HostFacts
    profile: Profile
    request: Request
    paths: Mapping[str, PlannedPath]
    version: SupportedVersion
    today: date

    def path_list(self) -> tuple[PlannedPath, ...]:
        return tuple(self.paths.values())


@dataclass(frozen=True)
class SharedRule:
    """One engine-independent rule: what it asks, how badly it matters, and how to ask."""

    identifier: str
    severity: Severity
    title: str
    check: Callable[[Context], Verdict]


# --------------------------------------------------------------------- reaching the host


def _reachable(context: Context) -> Verdict:
    """The facts describe the machine the request names.

    Whether the host answered at all is settled by there being a facts document: nothing
    else produces one. What is worth checking, and what nobody notices going wrong, is
    that the document describes the machine that is about to be changed.
    """
    found = context.facts.host
    wanted = context.request.host
    if found == wanted:
        return Verdict.satisfied(f"the facts describe {found}, which is the host requested")
    return Verdict.unmet(
        f"the facts describe {found}, but the request names {wanted}",
        "Collect the facts from the host being provisioned, or correct the host in the "
        "request. A plan built from one machine's facts describes that machine, and "
        "applying it to another is how a working instance gets a stranger's sizing.",
    )


def _privilege(context: Context) -> Verdict:
    """The account reaching the host can do the privileged work."""
    privileges = context.facts.privileges
    if privileges.can_escalate:
        return Verdict.satisfied(f"{privileges.user} can escalate")
    return Verdict.unmet(
        f"{privileges.user} cannot escalate",
        "Give the account Basewright connects with unattended privilege escalation on this "
        "host, or connect with one that has it. Installing packages, creating an account "
        "and writing under /etc are not optional parts of provisioning an instance.",
    )


# ------------------------------------------------------------------------ the ground


def _os_supported(context: Context) -> Verdict:
    """The distribution and its version are in the support matrix for this version."""
    host = context.facts.os
    supported = [
        f"{entry.distro} {version}"
        for entry in context.version.supported_os
        for version in entry.versions
    ]
    matched = any(
        entry.distro == host.distro and host.version in entry.versions
        for entry in context.version.supported_os
    )
    described = f"{host.distro} {host.version}"
    if matched:
        return Verdict.satisfied(f"{described} is supported by {_named(context)}")
    return Verdict.unmet(
        f"{described} is not supported by {_named(context)}; it supports "
        f"{', '.join(supported) or 'nothing'}",
        "Provision this instance on a supported operating system, or choose a version of "
        "the engine that supports this one. The support matrix is where an unsupported "
        "combination is argued about, and it is in the profile where a reviewer sees it.",
    )


def _arch_supported(context: Context) -> Verdict:
    """The processor architecture is one this version is published for."""
    arch = context.facts.arch
    if arch in context.version.arch:
        return Verdict.satisfied(f"{arch} is supported by {_named(context)}")
    return Verdict.unmet(
        f"{arch} is not supported by {_named(context)}; it supports "
        f"{', '.join(context.version.arch)}",
        "Provision this instance on a supported architecture. There is no build of this "
        "version for the one this host has, so there is nothing to install.",
    )


def _min_cores(context: Context) -> Verdict:
    """Enough cores for the engine to run as the profile expects it to."""
    required = context.profile.minimums.cores
    found = context.facts.cpu.cores
    if required is None:
        return Verdict.undecidable(
            "this profile states no minimum number of cores",
            "Declare minimums.cores in requirements.yml if the engine has a floor. Until "
            "it does, this rule has nothing to compare against and does not guess at one.",
        )
    if found >= required:
        return Verdict.satisfied(f"{found} cores, and {required} are required")
    return Verdict.unmet(
        f"{found} cores, and {required} are required",
        f"Give the host at least {required} cores, or provision this instance somewhere "
        "else. The number is the profile's, and the place to argue with it is the profile.",
    )


def _min_memory(context: Context) -> Verdict:
    """Enough memory for the engine to run as the profile expects it to.

    The requirement is quoted as the profile wrote it. Re-rendering ``2GB`` as ``1.9 GiB``
    is arithmetically right and makes a reader open the profile to check whether the two
    numbers are the same one, which is the opposite of what a refusal is for.
    """
    minimums = context.profile.minimums
    required = minimums.memory_bytes
    found = context.facts.memory.total_bytes
    if required is None or minimums.memory is None:
        return Verdict.undecidable(
            "this profile states no minimum memory",
            "Declare minimums.memory in requirements.yml if the engine has a floor. Until "
            "it does, this rule has nothing to compare against and does not guess at one.",
        )
    described = f"{render_bytes(found)} of memory, and {minimums.memory} is required"
    if found >= required:
        return Verdict.satisfied(described)
    return Verdict.unmet(
        described,
        f"Give the host at least {minimums.memory} of memory, or provision this instance "
        "somewhere else. Below the floor the engine starts and then fails under the first "
        "real workload, which is a worse outcome than a refusal.",
    )


# -------------------------------------------------------------------------- storage


def _paths_writable(context: Context) -> Verdict:
    """Every path the plan would create is on a mount that can be written to."""
    unusable: list[str] = []
    described: list[str] = []
    for planned in context.path_list():
        mount = context.facts.mount_for(planned.path)
        if mount is None:
            unusable.append(f"{planned.purpose} {planned.path} is on no mount this host reports")
        elif mount.read_only:
            unusable.append(
                f"{planned.purpose} {planned.path} is on {mount.path}, mounted read only"
            )
        else:
            described.append(f"{planned.purpose} on {mount.path}")

    if unusable:
        return Verdict.unmet(
            "; ".join(unusable),
            "Mount the filesystem read-write, or point the path at one that already is. "
            "Basewright creates directories; it does not remount anything underneath them.",
        )
    return Verdict.satisfied(f"{len(described)} paths, all on writable mounts")


def _free_space(context: Context) -> Verdict:
    """Every path that states a minimum has a mount with that much free."""
    short: list[str] = []
    checked = 0
    for planned in context.path_list():
        required = planned.min_free_bytes
        if required is None or planned.min_free is None:
            continue
        free = context.facts.free_bytes_for(planned.path)
        if free is None:
            continue
        checked += 1
        if free < required:
            mount = context.facts.mount_for(planned.path)
            where = mount.path if mount is not None else planned.path
            short.append(
                f"{planned.purpose} needs {planned.min_free} and {where} has "
                f"{render_bytes(free)} free"
            )

    if not checked:
        return Verdict.undecidable(
            "no path in this layout states how much free space it needs",
            "Declare min_free on the paths that have a floor. A threshold that refuses a "
            "host is a number someone has to be willing to defend, so it is stated in the "
            "profile rather than assumed here.",
        )
    if short:
        return Verdict.unmet(
            "; ".join(short),
            "Free the space, grow the filesystem, or point the path at a mount that has "
            "it. Provisioning onto a filesystem that is already short is how an instance "
            "fills its own disk during the first week.",
        )
    return Verdict.satisfied(f"{checked} paths meet the free space this profile requires")


def _separate_mounts(context: Context) -> Verdict:
    """Paths that would rather not share a filesystem do not share one."""
    sharing: list[str] = []
    considered = 0
    for planned in context.path_list():
        for other in planned.prefer_separate_from:
            companion = context.paths.get(other)
            if companion is None:
                continue
            considered += 1
            if context.facts.shares_mount_with(planned.path, companion.path):
                mount = context.facts.mount_for(planned.path)
                where = mount.path if mount is not None else "the same mount"
                sharing.append(f"{planned.purpose} and {other} both live on {where}")

    if not considered:
        return Verdict.undecidable(
            "no path in this layout asks to be kept apart from another",
            "Declare prefer_separate_from on the paths that should not share a filesystem.",
        )
    if sharing:
        return Verdict.unmet(
            "; ".join(sorted(set(sharing))),
            "Give them separate filesystems if the workload warrants it. Sharing costs "
            "failure isolation and makes one path able to fill the other; it is supported, "
            "and this is the record that it was chosen rather than overlooked.",
        )
    return Verdict.satisfied("every path that asks to be kept apart is on its own mount")


def _filesystem(context: Context) -> Verdict:
    """Every path is on a filesystem the engine is normally run on."""
    preferred = context.profile.preferences.filesystems
    if not preferred:
        return Verdict.undecidable(
            "this profile names no filesystems it prefers",
            "Declare preferences.filesystems in requirements.yml. Which filesystems an "
            "engine is habitually run on is knowledge about the engine, so the core does "
            "not hold an opinion about it.",
        )

    unusual: list[str] = []
    for planned in context.path_list():
        mount = context.facts.mount_for(planned.path)
        if mount is None or mount.filesystem in preferred:
            continue
        unusual.append(f"{planned.purpose} is on {mount.filesystem}")

    if unusual:
        return Verdict.unmet(
            f"{'; '.join(unusual)}; this profile prefers {', '.join(preferred)}",
            "Move the path to one of the preferred filesystems if it matters here. The "
            "engine will run on this one; the defaults were simply not tuned against it.",
        )
    return Verdict.satisfied(f"every path is on one of {', '.join(preferred)}")


# ----------------------------------------------------------------------- the machine


def _port_free(context: Context) -> Verdict:
    """Nothing is already listening on the port this instance would take."""
    port = context.request.port
    listening = context.facts.port_in_use(port)
    if listening is None:
        return Verdict.satisfied(f"nothing is listening on {port}")
    owner = listening.process or "an unidentified process"
    return Verdict.unmet(
        f"{owner} is listening on {port} at {listening.address}",
        "Choose another port for this instance, or stop what is on this one. Two things "
        "cannot share a port, and finding that out when the service fails to start tells "
        "you less than finding it out now.",
    )


def _not_installed(context: Context) -> Verdict:
    """Nothing the profile calls a conflict is already installed."""
    if not context.profile.conflicts:
        return Verdict.undecidable(
            "this profile declares nothing that would conflict",
            "Declare conflicts in requirements.yml. The core recognises no service by "
            "name, so what counts as an instance of this engine has to come from here.",
        )

    found: list[str] = []
    for service in context.facts.services:
        conflict = context.profile.conflicting(service.name)
        if conflict is None:
            continue
        version = f" {service.version}" if service.version else ""
        found.append(f"{service.name}{version} is {service.state} -- {conflict.description}")

    if found:
        return Verdict.unmet(
            "; ".join(found),
            "Remove the existing installation, or provision this instance on another host. "
            "Basewright never adopts, reconfigures or upgrades something it did not create, "
            "because it cannot tell what depends on it.",
        )
    return Verdict.satisfied(
        f"none of the {len(context.profile.conflicts)} conflicts this profile declares is present"
    )


def _repo_reachable(context: Context) -> Verdict:
    """The package repository this host would install from answers from this host."""
    packages = context.profile.packages_for(context.facts.os.family)
    if packages is None or packages.repository is None:
        return Verdict.undecidable(
            "this profile installs from the repositories the host already has",
            "Nothing to reach: no vendor repository is declared for this operating system "
            "family, so there is no third party for the host to depend on.",
        )

    repository = packages.repository
    reachable = context.facts.can_reach(repository.url)
    if reachable is None:
        return Verdict.undecidable(
            f"the host did not report whether it can reach {repository.name}",
            "Reaching a repository is proved from the host, which happens when the facts "
            "are collected over SSH. Until then this is unanswered rather than assumed, "
            "and the first task of apply is where it would otherwise be discovered.",
        )
    if reachable:
        return Verdict.satisfied(f"{repository.name} answers from this host")
    return Verdict.unmet(
        f"{repository.name} at {repository.url} does not answer from this host",
        "Open egress to the repository, or point the profile at a mirror this host can "
        "reach. Native packages come from the vendor, so a host that cannot reach one has "
        "nothing to install from.",
    )


def _locale_present(context: Context) -> Verdict:
    """The locale the instance is initialized with exists on the host."""
    locale = context.profile.default_locale
    if locale is None:
        return Verdict.undecidable(
            "this profile initializes without naming a locale",
            "Declare defaults.locale in profile.yml if initialization takes one.",
        )
    if context.facts.locale_present(locale):
        return Verdict.satisfied(f"{locale} is present")
    return Verdict.unmet(
        f"{locale} is not present; the host has {', '.join(context.facts.locales) or 'none'}",
        f"Generate {locale} on the host before provisioning. Initialization is the last "
        "step of apply and the first thing that fails without it, by which point the "
        "packages are installed and the account exists.",
    )


def _thp(context: Context) -> Verdict:
    """Transparent huge pages are set to something this engine is content with."""
    acceptable = context.profile.preferences.transparent_hugepages
    setting = context.facts.kernel.transparent_hugepages if context.facts.kernel else None
    if not acceptable:
        return Verdict.undecidable(
            "this profile states no transparent huge page setting it prefers",
            "Declare preferences.transparent_hugepages in requirements.yml. Engines "
            "disagree about this, so the core has no default to fall back on.",
        )
    if setting is None:
        return Verdict.undecidable(
            "the host did not report its transparent huge page setting",
            "Collect it, or accept that this is unanswered. A warning that guesses is "
            "worse than one that says it could not tell.",
        )
    if setting in acceptable:
        return Verdict.satisfied(f"transparent huge pages are {setting}")
    return Verdict.unmet(
        f"transparent huge pages are {setting}; this profile prefers {', '.join(acceptable)}",
        f"Set them to {' or '.join(acceptable)} persistently, in the boot configuration "
        "rather than only at run time. A setting that reverts on the next reboot is a "
        "problem that comes back at the worst moment.",
    )


def _swappiness(context: Context) -> Verdict:
    """The kernel is not more eager to swap than the engine wants it to be."""
    ceiling = context.profile.preferences.max_swappiness
    setting = context.facts.kernel.swappiness if context.facts.kernel else None
    if ceiling is None:
        return Verdict.undecidable(
            "this profile states no swappiness it prefers",
            "Declare preferences.max_swappiness in requirements.yml.",
        )
    if setting is None:
        return Verdict.undecidable(
            "the host did not report vm.swappiness",
            "Collect it, or accept that this is unanswered.",
        )
    described = f"vm.swappiness is {setting}, and this profile prefers at most {ceiling}"
    if setting <= ceiling:
        return Verdict.satisfied(described)
    return Verdict.unmet(
        described,
        f"Set vm.swappiness to {ceiling} or below, persistently. A database that has been "
        "swapped out answers queries at the speed of the disk it was swapped to.",
    )


def _time_sync(context: Context) -> Verdict:
    """The clock is being kept, and is currently keeping."""
    sync = context.facts.time_sync
    if sync is None:
        return Verdict.undecidable(
            "the host did not report a time synchronization service",
            "Collect it, or accept that this is unanswered.",
        )
    if sync.synchronized:
        return Verdict.satisfied(f"{sync.service} is synchronized")
    return Verdict.unmet(
        f"{sync.service} is present but not synchronized",
        "Get the clock synchronized before provisioning. Timestamps in the log, the "
        "ordering in a replicated setup and every certificate the instance presents all "
        "assume the machine knows what time it is.",
    )


def _firewall(context: Context) -> Verdict:
    """The firewall, if there is one, admits the port this instance will listen on."""
    firewall = context.facts.firewall
    if firewall is None:
        return Verdict.undecidable(
            "the host did not report a firewall",
            "Collect it, or accept that this is unanswered.",
        )
    port = context.request.port
    if not firewall.active:
        return Verdict.satisfied(f"{firewall.service} is inactive, so nothing filters {port}")
    if firewall.admits(port):
        return Verdict.satisfied(f"{firewall.service} is active and admits {port}")
    return Verdict.unmet(
        f"{firewall.service} is active and does not admit {port}",
        f"Open {port} to the clients that need it once the instance is running. Basewright "
        "does not change a firewall: what may reach a database is a decision about the "
        "network, and it is not this tool's to make.",
    )


# ------------------------------------------------------------------------- the version


def _eol(context: Context) -> Verdict:
    """The requested version is not about to stop being supported."""
    eol = context.version.eol
    remaining = eol - context.today
    described = f"{_named(context)} reaches end of life on {eol.isoformat()}"
    if remaining > EOL_HORIZON:
        return Verdict.satisfied(f"{described}, {remaining.days} days away")
    if remaining.days < 0:
        return Verdict.unmet(
            f"{described}, which has passed",
            "Provision a version that is still supported. This one receives no further "
            "fixes, including the security ones, and an instance created today will "
            "outlive the support that was left when it was.",
        )
    return Verdict.unmet(
        f"{described}, {remaining.days} days away",
        "Consider provisioning a newer version. An instance created now will still be "
        "running when this one stops receiving fixes, and the upgrade is easier to plan "
        "before there is data on it than after.",
    )


def _not_default(context: Context) -> Verdict:
    """The requested version is the one the profile would have chosen."""
    default = context.profile.default_version
    requested = context.request.version
    if requested == default:
        return Verdict.satisfied(f"{requested} is this profile's default")
    return Verdict.unmet(
        f"{requested} was requested; this profile defaults to {default}",
        "Nothing is wrong with this: the version is a person's choice and Basewright only "
        "validates it. The profile default is the version this engine's rules are tuned "
        "and tested against, so the difference is recorded rather than passed over.",
    )


def _named(context: Context) -> str:
    """The engine and version as a report names them, in the profile's own words."""
    return f"{context.profile.display_name} {context.request.version}"


def _block(identifier: str, title: str, check: Callable[[Context], Verdict]) -> SharedRule:
    """A rule that refuses the host when it is not met."""
    return SharedRule(identifier, Severity.BLOCK, title, check)


def _warn(identifier: str, title: str, check: Callable[[Context], Verdict]) -> SharedRule:
    """A rule that is reported and acknowledged when it is not met."""
    return SharedRule(identifier, Severity.WARN, title, check)


#: The twenty shared rules, in the order the brief lists them. Blocks first, because a
#: reader wants to know what refuses a host before what merely notes something about it.
SHARED_RULES: Sequence[SharedRule] = (
    _block("host.reachable", "The facts describe the host requested", _reachable),
    _block("host.privilege", "The account can do privileged work", _privilege),
    _block("os.supported", "The operating system is supported", _os_supported),
    _block("arch.supported", "The architecture is supported", _arch_supported),
    _block("cpu.min_cores", "Enough cores for this engine", _min_cores),
    _block("mem.min_total", "Enough memory for this engine", _min_memory),
    _block("disk.paths_writable", "Every path is on a writable mount", _paths_writable),
    _block("disk.free_space", "Every path has the free space it needs", _free_space),
    _block("port.free", "The port is not already taken", _port_free),
    _block("engine.not_installed", "Nothing conflicting is installed", _not_installed),
    _block("repo.reachable", "The package repository answers", _repo_reachable),
    _block("locale.present", "The locale initialization needs exists", _locale_present),
    _warn("disk.separate_mounts", "Separation of the paths that ask for it", _separate_mounts),
    _warn("disk.filesystem", "Paths are on a usual filesystem", _filesystem),
    _warn("os.thp", "Transparent huge pages are as preferred", _thp),
    _warn("os.swappiness", "The kernel is not eager to swap", _swappiness),
    _warn("time.sync", "The clock is synchronized", _time_sync),
    _warn("version.eol", "The version has support left", _eol),
    _warn("version.not_default", "The version is the profile default", _not_default),
    _warn("firewall.state", "The firewall admits the port", _firewall),
)
