"""The vocabulary an expression written in a profile is evaluated against.

One vocabulary, not two. A gate rule asking whether a host is fit and a sizing rule
working out how large a cache should be read the same names for the same things, because
a profile author who has learned one has learned the other, and because a fact that means
something different to the two would be a fact nobody could reason about.

Everything an expression can reach is built here, and it is all plain values in plain
mappings: no object of ours ever enters an expression, which is what makes the evaluator
safe by construction rather than by vigilance.

The shape is fixed whatever a collector managed to answer. A fact the contract defines
but the host did not report is present as :data:`~basewright.expressions.UNREPORTED`
rather than absent, so that reading it skips the rule while a misspelling still raises.
Those are different mistakes and they get different answers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from basewright.expressions import UNREPORTED, base_scope
from basewright.facts.model import HostFacts
from basewright.layout import PlannedPath
from basewright.profiles.model import Profile
from basewright.request import Request


def build_scope(
    facts: HostFacts,
    profile: Profile,
    request: Request,
    paths: Mapping[str, PlannedPath],
) -> dict[str, Any]:
    """Everything a rule may read about this host, this request and this profile."""
    scope = base_scope()
    scope["host"] = _host(facts)
    scope["request"] = _request(request)
    scope["profile"] = _profile(profile)
    scope["path"] = {purpose: _path(facts, planned) for purpose, planned in paths.items()}
    return scope


def _host(facts: HostFacts) -> dict[str, Any]:
    return {
        "name": facts.host,
        "arch": facts.arch,
        "locales": facts.locales,
        "os": {
            "family": facts.os.family,
            "distro": facts.os.distro,
            "version": facts.os.version,
            "codename": _or_unreported(facts.os.codename),
            "pretty_name": _or_unreported(facts.os.pretty_name),
            "kernel": _or_unreported(facts.os.kernel),
        },
        "cpu": {
            "cores": facts.cpu.cores,
            "threads": _or_unreported(facts.cpu.threads),
        },
        "memory": {
            "total_bytes": facts.memory.total_bytes,
            "available_bytes": _or_unreported(facts.memory.available_bytes),
            "swap_bytes": _or_unreported(facts.memory.swap_bytes),
        },
        "kernel": {
            "swappiness": _or_unreported(facts.kernel and facts.kernel.swappiness),
            "transparent_hugepages": _or_unreported(
                facts.kernel and facts.kernel.transparent_hugepages
            ),
            "overcommit_memory": _or_unreported(facts.kernel and facts.kernel.overcommit_memory),
        },
        "time_sync": {
            "service": _or_unreported(facts.time_sync and facts.time_sync.service),
            "synchronized": _or_unreported(facts.time_sync and facts.time_sync.synchronized),
        },
        "firewall": {
            "service": _or_unreported(facts.firewall and facts.firewall.service),
            "active": _or_unreported(facts.firewall and facts.firewall.active),
        },
        "privileges": {
            "user": facts.privileges.user,
            "can_escalate": facts.privileges.can_escalate,
        },
    }


def _request(request: Request) -> dict[str, Any]:
    return {
        "host": request.host,
        "engine": request.engine,
        "version": request.version,
        "environment": request.environment,
        "instance": request.instance,
        "port": request.port,
        "chosen_version": request.chosen_version,
    }


def _profile(profile: Profile) -> dict[str, Any]:
    return {
        "engine": profile.engine,
        "version": profile.profile_version,
        "default_version": profile.default_version,
        "default_port": profile.default_port,
        "default_instance": profile.default_instance,
        "locale": _or_unreported(profile.default_locale),
    }


def _path(facts: HostFacts, planned: PlannedPath) -> dict[str, Any]:
    """One planned path, together with what is known about the mount carrying it.

    A path the host reports no mount for is not an error here. It is a blocking shared
    rule of its own, and a profile rule that also reads the path skips rather than
    guessing at a filesystem nobody described.
    """
    mount = facts.mount_for(planned.path)
    if mount is None:
        return {
            "path": planned.path,
            "mount": UNREPORTED,
            "filesystem": UNREPORTED,
            "free_bytes": UNREPORTED,
            "total_bytes": UNREPORTED,
            "rotational": UNREPORTED,
            "read_only": UNREPORTED,
        }
    return {
        "path": planned.path,
        "mount": mount.path,
        "filesystem": mount.filesystem,
        "free_bytes": mount.free_bytes,
        "total_bytes": mount.total_bytes,
        "rotational": _or_unreported(mount.rotational),
        "read_only": mount.read_only,
    }


def _or_unreported(value: Any) -> Any:
    """A value, or the marker that says the host was not asked or did not answer."""
    return UNREPORTED if value is None else value
