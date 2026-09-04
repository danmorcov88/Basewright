"""Reading a profile directory, and refusing it clearly when it does not hold together.

Loading happens in three passes, and each one runs to completion before the next begins,
so a profile author sees every problem of a kind at once rather than one per run:

1. **Read.** Each of the eight files is parsed as YAML. A file that is missing, unreadable
   or not a mapping is a problem in its own right.
2. **Validate.** Each document is checked against its schema, which is closed, so an
   unknown key is an error rather than something quietly ignored.
3. **Reconcile.** The checks a single-file schema cannot express, because they are
   agreements *between* files: that every file names the same engine, that the default
   version is one of the versions, that every operating system family the profile relies
   on is declared and can actually be installed on, and that no identifier is used twice.

Only a profile that survives all three becomes a :class:`~basewright.profiles.model.Profile`.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from basewright.expressions import base_scope
from basewright.profiles.errors import InvalidProfileError, MissingProfileError
from basewright.profiles.model import (
    ConfigurationFile,
    Conflict,
    GateRule,
    Initialization,
    InitializationSetting,
    Minimums,
    PackageSet,
    PathSpec,
    Preferences,
    Profile,
    Repository,
    Secret,
    ServiceAccount,
    SizingRule,
    SupportedOS,
    SupportedVersion,
    Tunable,
    VerifyCheck,
)
from basewright.profiles.schema import PROFILE_FILES, schema_name_for
from basewright.report.problems import Problem
from basewright.schema import problems_in

Document = dict[str, Any]
Documents = dict[str, Document]


def load_profile(directory: Path) -> Profile:
    """Read, validate and reconcile one profile directory.

    Raises :class:`MissingProfileError` if there is nothing there, and :class:`InvalidProfileError`
    carrying every problem found if what is there does not hold together.
    """
    if not directory.is_dir():
        raise MissingProfileError(directory)

    documents, problems = _read(directory)
    if problems:
        raise InvalidProfileError(directory, problems)

    problems = [
        problem
        for name, document in documents.items()
        for problem in problems_in(document, schema_name=schema_name_for(name), file=name)
    ]
    if problems:
        raise InvalidProfileError(directory, problems)

    problems = list(_reconcile(directory, documents))
    if problems:
        raise InvalidProfileError(directory, problems)

    return _build(directory, documents)


def load_profiles(directory: Path) -> list[Profile]:
    """Load every profile directory found directly under ``directory``.

    Used to check a whole tree of profiles at once. An invalid profile still raises, so a
    tree is either entirely loadable or the run says which member of it is not.
    """
    if not directory.is_dir():
        raise MissingProfileError(directory)
    return [load_profile(child) for child in sorted(directory.iterdir()) if child.is_dir()]


def profile_directories(directory: Path) -> list[Path]:
    """Every immediate subdirectory of ``directory``, in a stable order."""
    if not directory.is_dir():
        raise MissingProfileError(directory)
    return [child for child in sorted(directory.iterdir()) if child.is_dir()]


# ------------------------------------------------------------------------------- reading


def _read(directory: Path) -> tuple[Documents, list[Problem]]:
    """Parse every file of the profile, collecting the ones that could not be read."""
    documents: Documents = {}
    problems: list[Problem] = []

    for name in PROFILE_FILES:
        path = directory / name
        if not path.is_file():
            problems.append(
                Problem(
                    file=name,
                    location="",
                    message="is missing",
                    hint=(
                        "A profile is made of all eight files. An engine that needs "
                        "nothing from one of them still declares that, so a reader can "
                        "tell an empty answer from a forgotten one."
                    ),
                )
            )
            continue

        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            problems.append(
                Problem(
                    file=name,
                    location="",
                    message="is not valid YAML",
                    hint=" ".join(str(error).split()),
                )
            )
            continue

        if not isinstance(document, dict):
            problems.append(
                Problem(
                    file=name,
                    location="",
                    message=f"is {type(document).__name__}, not a mapping of keys to values",
                    hint="Every file of a profile is a mapping at the top level.",
                )
            )
            continue

        documents[name] = document

    return documents, problems


# --------------------------------------------------------------------------- reconciling


def _reconcile(directory: Path, documents: Documents) -> Iterator[Problem]:
    """The agreements between files, which no single file's schema can enforce."""
    profile = documents["profile.yml"]
    engine = str(profile["engine"])
    families = [str(family) for family in profile["os_families"]]

    yield from _engine_agrees(documents, engine)
    yield from _default_version_exists(documents["support-matrix.yml"])
    yield from _families_are_declared(documents, families)
    yield from _families_are_installable(documents["packages.yml"], families)
    yield from _identifiers_are_unique(documents)
    yield from _parameters_are_set_once(documents["sizing.yml"])
    yield from _parameters_do_not_shadow_the_vocabulary(documents["sizing.yml"])
    yield from _separations_name_real_paths(documents["layout.yml"])
    yield from _one_file_carries_the_parameters(documents["apply.yml"])
    yield from _templates_exist(directory, documents["apply.yml"])


def _engine_agrees(documents: Documents, engine: str) -> Iterator[Problem]:
    for name, document in documents.items():
        if name == "profile.yml":
            continue
        found = str(document["engine"])
        if found != engine:
            yield Problem(
                file=name,
                location="engine",
                message=f"is {found!r}, but profile.yml declares {engine!r}",
                hint=(
                    "Every file of a profile repeats the engine it belongs to, so that a "
                    "file copied into the wrong profile is caught here rather than found "
                    "later in a plan that does not make sense."
                ),
            )


def _default_version_exists(matrix: Document) -> Iterator[Problem]:
    default = str(matrix["default_version"])
    known = [str(entry["version"]) for entry in matrix["versions"]]
    if default not in known:
        yield Problem(
            file="support-matrix.yml",
            location="default_version",
            message=f"is {default!r}, which is not one of the versions listed",
            hint=(
                "The default is what a request that does not name a version gets, so it "
                f"has to be supported. Listed versions are: {', '.join(known)}."
            ),
        )


def _families_are_declared(documents: Documents, families: Iterable[str]) -> Iterator[Problem]:
    declared = set(families)
    matrix = documents["support-matrix.yml"]
    for index, entry in enumerate(matrix["versions"]):
        for position, supported in enumerate(entry["supported_os"]):
            family = str(supported["family"])
            if family not in declared:
                yield Problem(
                    file="support-matrix.yml",
                    location=f"versions[{index}].supported_os[{position}].family",
                    message=f"is {family!r}, which profile.yml does not declare",
                    hint=(
                        "profile.yml is the single list of families the profile supports. "
                        "Add it there as well, or drop it here: a matrix that claims "
                        f"ground the profile cannot install on is worse than one that "
                        f"does not. Declared families are: {', '.join(sorted(declared))}."
                    ),
                )


def _families_are_installable(packages: Document, families: Iterable[str]) -> Iterator[Problem]:
    covered = set(packages["families"])
    for family in sorted(set(families) - covered):
        yield Problem(
            file="packages.yml",
            location=f"families.{family}",
            message="is declared in profile.yml but has no packages here",
            hint=(
                "Give the family a repository, a package list and a service unit, or stop "
                "declaring it. A profile that claims a family it cannot install on refuses "
                "at apply time, which is the latest possible moment to find out."
            ),
        )


def _identifiers_are_unique(documents: Documents) -> Iterator[Problem]:
    """Identifiers are what a report prints and what a person greps for. Two of the same
    identifier means one of the two is invisible."""
    sources: tuple[tuple[str, str, str], ...] = (
        ("requirements.yml", "rules", "id"),
        ("sizing.yml", "rules", "id"),
        ("apply.yml", "configuration", "id"),
        ("verify.yml", "checks", "id"),
    )
    seen: dict[str, tuple[str, str]] = {}
    for name, collection, key in sources:
        for index, entry in enumerate(documents[name][collection]):
            identifier = str(entry[key])
            first = seen.get(identifier)
            if first is None:
                seen[identifier] = (name, f"{collection}[{index}]")
                continue
            first_file, first_location = first
            used = first_location if first_file == name else f"{first_file} {first_location}"
            yield Problem(
                file=name,
                location=f"{collection}[{index}].{key}",
                message=f"{identifier!r} is already used by {used}",
                hint=(
                    "An identifier names one rule for the life of the profile: it is what "
                    "a refusal prints and what someone searches for six months later. Two "
                    "rules cannot share one."
                ),
            )


def _parameters_are_set_once(sizing: Document) -> Iterator[Problem]:
    seen: dict[str, int] = {}
    for index, rule in enumerate(sizing["rules"]):
        parameter = str(rule["parameter"])
        if parameter in seen:
            yield Problem(
                file="sizing.yml",
                location=f"rules[{index}].parameter",
                message=f"sets {parameter!r}, which rules[{seen[parameter]}] already sets",
                hint=(
                    "Two rules setting one parameter means the plan reports one reason and "
                    "the instance gets the other value. Combine them into a single rule "
                    "whose expression covers both cases."
                ),
            )
            continue
        seen[parameter] = index


#: The names a rule's scope is built out of, which a sizing parameter therefore cannot be
#: called: an expression reading one would reach the group and never the parameter. The
#: unit constants are the other half, and they come from the expression language itself.
#: A test holds this list against the scope the gate engine actually builds.
_RESERVED_GROUPS: tuple[str, ...] = ("host", "request", "profile", "path")


def _parameters_do_not_shadow_the_vocabulary(sizing: Document) -> Iterator[Problem]:
    """A parameter cannot be named after something an expression already reads.

    A later rule referring to it by name would reach the group of facts or the unit
    constant instead, silently, and be sized from the wrong thing.
    """
    reserved = set(base_scope()) | set(_RESERVED_GROUPS)
    for index, rule in enumerate(sizing["rules"]):
        parameter = str(rule["parameter"])
        if parameter in reserved:
            yield Problem(
                file="sizing.yml",
                location=f"rules[{index}].parameter",
                message=f"is {parameter!r}, which is already a name every expression reads",
                hint=(
                    "A rule referring to this parameter would reach the built-in name "
                    "instead and be sized from it without complaining. Names taken are: "
                    f"{', '.join(sorted(reserved))}."
                ),
            )


def _one_file_carries_the_parameters(apply: Document) -> Iterator[Problem]:
    """At most one configuration file may claim the sized parameters.

    Two would mean the plan promising the same values twice, and nothing saying which
    file the instance actually reads them from.
    """
    carriers = [
        (index, str(entry["id"]))
        for index, entry in enumerate(apply["configuration"])
        if entry.get("carries_parameters", False)
    ]
    for index, _ in carriers[1:]:
        yield Problem(
            file="apply.yml",
            location=f"configuration[{index}].carries_parameters",
            message=f"is already set on {carriers[0][1]!r}",
            hint=(
                "The sized parameters are written into one file. Two files claiming them "
                "leaves nothing to say which one the instance reads."
            ),
        )


def _templates_exist(directory: Path, apply: Document) -> Iterator[Problem]:
    """Every template a configuration file names has to be in the profile.

    A plan that promises a file the profile cannot render is a promise broken at apply
    time, on somebody else's machine, halfway through.
    """
    for index, entry in enumerate(apply["configuration"]):
        template = str(entry["template"])
        if not (directory / "templates" / template).is_file():
            yield Problem(
                file="apply.yml",
                location=f"configuration[{index}].template",
                message=f"is {template!r}, which templates/ does not hold",
                hint=(
                    "Add the template, or stop naming it. A plan promising a file that "
                    "cannot be rendered refuses halfway through apply instead of here."
                ),
            )


# ------------------------------------------------------------------------------ building


def _separations_name_real_paths(layout: Document) -> Iterator[Problem]:
    """A path can only prefer to be separate from a path the layout defines.

    A purpose that does not exist reads as a rule about storage and is silently no rule
    at all, which is the worst of the two ways to be wrong about a warning.
    """
    paths: Mapping[str, Document] = layout["paths"]
    for purpose, spec in paths.items():
        for position, other in enumerate(spec.get("prefer_separate_from", [])):
            if str(other) == purpose:
                yield Problem(
                    file="layout.yml",
                    location=f"paths.{purpose}.prefer_separate_from[{position}]",
                    message=f"is {purpose!r}, which is the path itself",
                    hint="A path always shares a mount with itself. Name a different purpose.",
                )
            elif str(other) not in paths:
                yield Problem(
                    file="layout.yml",
                    location=f"paths.{purpose}.prefer_separate_from[{position}]",
                    message=f"is {other!r}, which this layout does not define",
                    hint=(
                        "A path can only be kept apart from one that exists. Paths here "
                        f"are: {', '.join(sorted(paths))}."
                    ),
                )


def _build(directory: Path, documents: Documents) -> Profile:
    """Turn eight validated documents into one profile. No decisions are taken here."""
    profile = documents["profile.yml"]
    matrix = documents["support-matrix.yml"]
    layout = documents["layout.yml"]
    requirements = documents["requirements.yml"]

    return Profile(
        root=directory,
        engine=profile["engine"],
        display_name=profile["display_name"],
        profile_version=profile["profile_version"],
        summary=profile["summary"],
        os_families=tuple(profile["os_families"]),
        default_port=int(profile["defaults"]["port"]),
        default_instance=profile["defaults"]["instance"],
        default_locale=profile["defaults"].get("locale"),
        documentation=profile.get("documentation"),
        default_version=matrix["default_version"],
        versions=tuple(_version(entry) for entry in matrix["versions"]),
        gates=tuple(_gate(rule) for rule in requirements["rules"]),
        minimums=_minimums(requirements.get("minimums", {})),
        preferences=_preferences(requirements.get("preferences", {})),
        conflicts=tuple(_conflict(entry) for entry in requirements.get("conflicts", [])),
        paths=_paths(layout["paths"]),
        service_account=_service_account(layout["service_account"]),
        sizing=tuple(_sizing(rule) for rule in documents["sizing.yml"]["rules"]),
        packages=_packages(documents["packages.yml"]["families"]),
        configuration=tuple(
            _configuration(entry) for entry in documents["apply.yml"]["configuration"]
        ),
        tunables=tuple(_tunable(entry) for entry in documents["apply.yml"].get("tunables", [])),
        initialization=_initialization(documents["apply.yml"].get("initialization")),
        secrets=tuple(_secret(entry) for entry in documents["apply.yml"].get("secrets", [])),
        checks=tuple(_check(entry) for entry in documents["verify.yml"]["checks"]),
    )


def _version(entry: Document) -> SupportedVersion:
    return SupportedVersion(
        version=entry["version"],
        eol=date.fromisoformat(entry["eol"]),
        status=entry.get("status", "supported"),
        arch=tuple(entry["arch"]),
        supported_os=tuple(
            SupportedOS(
                family=supported["family"],
                distro=supported["distro"],
                versions=tuple(supported["versions"]),
            )
            for supported in entry["supported_os"]
        ),
    )


def _gate(rule: Document) -> GateRule:
    return GateRule(
        identifier=rule["id"],
        severity=rule["severity"],
        title=rule["title"],
        expr=rule["expr"],
        remediation=rule["remediation"],
        applies_to=rule.get("applies_to"),
    )


def _minimums(minimums: Document) -> Minimums:
    return Minimums(cores=minimums.get("cores"), memory=minimums.get("memory"))


def _preferences(preferences: Document) -> Preferences:
    return Preferences(
        filesystems=tuple(preferences.get("filesystems", ())),
        transparent_hugepages=tuple(preferences.get("transparent_hugepages", ())),
        max_swappiness=preferences.get("max_swappiness"),
    )


def _conflict(entry: Document) -> Conflict:
    return Conflict(
        service=entry["service"],
        description=" ".join(str(entry["description"]).split()),
        match=entry.get("match", "exact"),
    )


def _sizing(rule: Document) -> SizingRule:
    return SizingRule(
        identifier=rule["id"],
        parameter=rule["parameter"],
        expr=rule["expr"],
        why=" ".join(str(rule["why"]).split()),
        unit=rule.get("unit", "count"),
        minimum=rule.get("min"),
        maximum=rule.get("max"),
        warn_above=rule.get("warn_above"),
        round_to=rule.get("round_to"),
    )


def _paths(paths: Mapping[str, Document]) -> dict[str, PathSpec]:
    return {
        purpose: PathSpec(
            purpose=purpose,
            default=spec["default"],
            mode=spec["mode"],
            min_free=spec.get("min_free"),
            prefer_separate_from=tuple(spec.get("prefer_separate_from", ())),
            description=" ".join(str(spec.get("description", "")).split()),
        )
        for purpose, spec in paths.items()
    }


def _service_account(account: Document) -> ServiceAccount:
    return ServiceAccount(
        name=account["name"],
        create_if_missing=bool(account["create_if_missing"]),
        shell=account["shell"],
        group=account.get("group"),
        home=account.get("home"),
    )


def _packages(families: Mapping[str, Document]) -> dict[str, PackageSet]:
    return {
        family: PackageSet(
            family=family,
            packages=tuple(entry["packages"]),
            service=entry["service"],
            repository=_repository(entry.get("repository")),
        )
        for family, entry in families.items()
    }


def _repository(repository: Document | None) -> Repository | None:
    if repository is None:
        return None
    return Repository(
        name=repository["name"],
        url=repository["url"],
        key_url=repository.get("key_url"),
        suite=repository.get("suite"),
        components=tuple(repository.get("components", ())),
        gpg_check=bool(repository.get("gpg_check", True)),
    )


def _configuration(entry: Document) -> ConfigurationFile:
    return ConfigurationFile(
        identifier=entry["id"],
        template=entry["template"],
        destination=entry["destination"],
        mode=entry["mode"],
        description=" ".join(str(entry["description"]).split()),
        owner=entry.get("owner"),
        carries_parameters=bool(entry.get("carries_parameters", False)),
    )


def _initialization(entry: Document | None) -> Initialization | None:
    """What creating the instance takes, or None for an engine that needs nothing.

    Absent is a real answer here: an engine whose packages leave a running server behind
    them has nothing to initialize, and a plan for one carries no initialization section
    rather than an empty one nobody would know how to read.
    """
    if entry is None:
        return None
    return Initialization(
        description=" ".join(str(entry["description"]).split()),
        settings=tuple(
            InitializationSetting(
                name=setting["name"],
                value=setting["value"],
                why=" ".join(str(setting["why"]).split()),
            )
            for setting in entry["settings"]
        ),
    )


def _tunable(entry: Document) -> Tunable:
    return Tunable(
        name=entry["name"],
        value=entry["value"],
        why=" ".join(str(entry["why"]).split()),
        observed=entry.get("observed"),
    )


def _secret(entry: Document) -> Secret:
    return Secret(
        name=entry["name"],
        location=entry["location"],
        description=" ".join(str(entry["description"]).split()),
    )


def _check(entry: Document) -> VerifyCheck:
    return VerifyCheck(
        identifier=entry["id"],
        kind=entry["kind"],
        title=entry["title"],
        remediation=" ".join(str(entry["remediation"]).split()),
        expr=entry.get("expr"),
    )
