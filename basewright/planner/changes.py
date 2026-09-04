"""What apply would do, worked out before anything is touched.

Four of the plan's sections are built here. Three of them are what apply executes --
which packages come from which repository, which configuration files are rendered where,
which host settings are set to what -- and the fourth is the narrative a person reads
before approving any of it. They are separate on purpose: a list written for a machine to
follow and a list written for somebody to sign are not the same list, and collapsing them
means one of the two is wrong.

Nothing here knows what any of it is for. A package name, a service unit, a destination
and the location of a secret are strings a profile wrote with the parts that vary left
open, and filling those in is all that happens to them. The order the changes come in is
the order the phases run in -- repository, packages, account, directories, configuration,
host settings, service -- which is a fact about provisioning rather than about any engine.

There is no removal. Apply creates and configures; it does not drop a data directory and
does not overwrite a file without leaving a timestamped copy beside it, so the vocabulary
of a change is add and modify and there is no third word for the profile to reach for.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from basewright.expressions import Expression, ExpressionError, Unreported
from basewright.facts.model import HostFacts
from basewright.layout import PlannedPath
from basewright.placeholders import substitute
from basewright.planner.errors import PlanError
from basewright.planner.sizing import Sized
from basewright.profiles.model import PackageSet, Profile, Tunable
from basewright.request import Request

__all__ = ["Actions", "plan_actions"]


@dataclass(frozen=True)
class Actions:
    """Everything apply would do: three sections it executes, and one a person reads."""

    packages: dict[str, Any]
    configuration: tuple[dict[str, Any], ...]
    initialization: dict[str, Any] | None
    tunables: tuple[dict[str, Any], ...]
    secrets: tuple[dict[str, Any], ...]
    changes: tuple[dict[str, Any], ...]


def plan_actions(
    facts: HostFacts,
    profile: Profile,
    request: Request,
    paths: Mapping[str, PlannedPath],
    parameters: Sequence[Sized],
    scope: Mapping[str, Any],
) -> Actions:
    """Resolve everything the profile leaves open, for this host and this request."""
    values = _vocabulary(facts, request)
    packages = _packages_for(facts, profile)
    account = profile.service_account
    owner = account.name
    group = account.group or account.name

    installed = tuple(substitute(name, values, noun="a package name") for name in packages.packages)
    service = substitute(packages.service, values, noun="a service unit")

    configuration = tuple(
        {
            "id": entry.identifier,
            "template": entry.template,
            "destination": substitute(entry.destination, values, noun="a path"),
            "mode": entry.mode,
            "owner": entry.owner or owner,
            "group": group,
            "carries_parameters": entry.carries_parameters,
            "description": entry.description,
        }
        for entry in profile.configuration
    )

    initialization = _initialization(profile)
    tunables = tuple(_tunable(tunable, scope) for tunable in profile.tunables)

    secrets = tuple(
        {
            "name": secret.name,
            "location": substitute(secret.location, values, noun="a secret's location"),
            "description": secret.description,
        }
        for secret in profile.secrets
    )

    return Actions(
        packages=_packages_section(packages, values, installed, service),
        configuration=configuration,
        initialization=initialization,
        tunables=tunables,
        secrets=secrets,
        changes=_changes(
            packages=packages,
            values=values,
            installed=installed,
            service=service,
            account_name=owner,
            create_account=account.create_if_missing,
            paths=paths,
            initialization=initialization,
            configuration=configuration,
            tunables=tunables,
            parameters=parameters,
        ),
    )


# ------------------------------------------------------------------------- resolving


def _vocabulary(facts: HostFacts, request: Request) -> dict[str, str | None]:
    """Every name a profile may leave open, and what this run fills it in with.

    A name the host did not report is present and empty rather than absent, so that a
    template depending on it is refused for the right reason.
    """
    return {
        "engine": request.engine,
        "instance": request.instance,
        "version": request.version,
        "environment": request.environment,
        "host": request.host,
        "os.family": facts.os.family,
        "os.distro": facts.os.distro,
        "os.version": facts.os.version,
        "os.major": facts.os.major,
        "os.codename": facts.os.codename,
    }


def _packages_for(facts: HostFacts, profile: Profile) -> PackageSet:
    packages = profile.packages_for(facts.os.family)
    if packages is None:
        declared = ", ".join(sorted(profile.packages)) or "none"
        raise PlanError(
            f"This profile has no packages for the {facts.os.family} family, which is what "
            f"{facts.host} runs. It has packages for: {declared}."
        )
    return packages


def _packages_section(
    packages: PackageSet,
    values: Mapping[str, str | None],
    installed: Sequence[str],
    service: str,
) -> dict[str, Any]:
    """What to install, from where, and what service results."""
    section: dict[str, Any] = {
        "family": packages.family,
        "install": list(installed),
        "service": service,
    }
    repository = packages.repository
    if repository is not None:
        entry: dict[str, Any] = {
            "name": repository.name,
            "url": substitute(repository.url, values, noun="a repository url"),
            "gpg_check": repository.gpg_check,
        }
        if repository.key_url is not None:
            entry["key_url"] = repository.key_url
        if repository.suite is not None:
            entry["suite"] = substitute(repository.suite, values, noun="a repository suite")
        if repository.components:
            entry["components"] = list(repository.components)
        section["repository"] = entry
    return section


def _initialization(profile: Profile) -> dict[str, Any] | None:
    """What creating the instance takes, or nothing for an engine that needs no creating.

    The locale comes from the profile's defaults rather than from this section, because a
    shared rule already blocks a host that has not got it and two spellings of one locale
    is two things to keep in step. Everything else is carried through untouched: the core
    does not know what any of these names mean and does not need to.
    """
    if profile.initialization is None:
        return None

    section: dict[str, Any] = {"description": profile.initialization.description}
    if profile.default_locale is not None:
        section["locale"] = profile.default_locale
    section["settings"] = [
        {"name": setting.name, "value": setting.value, "why": setting.why}
        for setting in profile.initialization.settings
    ]
    return section


def _tunable(tunable: Tunable, scope: Mapping[str, Any]) -> dict[str, Any]:
    """One host setting, what it will be, and what it is now if the host said.

    ``observed`` is an expression rather than a name mapped in here, so that a profile can
    ask for a setting nobody anticipated without this module growing a table of them.
    """
    entry: dict[str, Any] = {
        "name": tunable.name,
        "value": tunable.value,
        "why": tunable.why,
    }
    if tunable.observed is None:
        return entry

    try:
        entry["observed"] = Expression.parse(tunable.observed).evaluate(scope)
    except Unreported:
        return entry
    except ExpressionError as error:
        raise PlanError(
            f"{tunable.name}: {error}\n"
            f"  in apply.yml, what reads the setting as it is now: {tunable.observed!r}"
        ) from error
    return entry


# -------------------------------------------------------------------------- narrating


def _changes(
    *,
    packages: PackageSet,
    values: Mapping[str, str | None],
    installed: Sequence[str],
    service: str,
    account_name: str,
    create_account: bool,
    paths: Mapping[str, PlannedPath],
    initialization: Mapping[str, Any] | None,
    configuration: Sequence[Mapping[str, Any]],
    tunables: Sequence[Mapping[str, Any]],
    parameters: Sequence[Sized],
) -> tuple[dict[str, Any], ...]:
    """The list somebody reads before approving it, in the order the phases run."""
    changes: list[dict[str, Any]] = []

    if packages.repository is not None:
        name = packages.repository.name
        url = substitute(packages.repository.url, values, noun="a repository url")
        changes.append(_add(f"add package repository {name} ({url})"))

    changes.append(_add(f"install {', '.join(installed)}"))

    if create_account:
        changes.append(_add(f"create service account {account_name}, unless it already exists"))

    changes.append(_add(f"create {_counted(len(paths), 'directory', 'directories')}"))

    if initialization is not None:
        changes.append(_add(f"initialize the instance ({_settings_of(initialization)})"))

    for entry in configuration:
        detail = ""
        if entry["carries_parameters"]:
            detail = f" ({_counted(len(parameters), 'parameter', 'parameters')})"
        changes.append(_add(f"write {entry['destination']}{detail}"))

    for tunable in tunables:
        changes.extend(_tunable_change(tunable))

    changes.append(_add(f"enable and start {service}"))
    return tuple(changes)


def _tunable_change(tunable: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One host setting, said the way a reviewer wants to read it.

    A setting already at the value the profile asks for is not a change, so it is not in
    this list. It stays in the section apply executes, because apply holds the host to it
    whether or not it had to move.
    """
    wanted = _rendered(tunable["value"])
    if "observed" not in tunable:
        return [_add(f"set {tunable['name']} to {wanted}")]

    observed = _rendered(tunable["observed"])
    if observed == wanted:
        return []
    return [
        {
            "action": "modify",
            "description": f"set {tunable['name']}",
            "from": observed,
            "to": wanted,
        }
    ]


def _settings_of(initialization: Mapping[str, Any]) -> str:
    """The choices creating the instance is made with, spelled out rather than counted.

    A configuration file's change says how many parameters it carries, because nobody
    reviews twenty-three of them in a list of changes. These are three or four, they
    cannot be changed afterwards, and they are exactly what somebody approving a plan is
    reading this line to find out.
    """
    chosen = [
        f"{name}={_rendered(initialization[name])}"
        for name in ("locale",)
        if name in initialization
    ]
    chosen.extend(
        f"{setting['name']}={_rendered(setting['value'])}" for setting in initialization["settings"]
    )
    return ", ".join(chosen)


def _add(description: str) -> dict[str, Any]:
    return {"action": "add", "description": description}


def _rendered(value: Any) -> str:
    """A setting's value as the plan prints it, in the words the host uses."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _counted(total: int, singular: str, plural: str) -> str:
    return f"{total} {singular if total == 1 else plural}"
