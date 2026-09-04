"""What was asked for, resolved against what the profile supports.

A request names a host, an engine version, an environment and an instance. Some of that
is supplied and the rest comes from the profile's defaults, and the difference matters
enough to be recorded: a version a person chose and a version nobody chose are not the
same decision, and the plan says which it was.

Resolution is also where a version the support matrix does not list is refused. That
happens before any gate runs, so every rule can read the matrix entry for the requested
version without checking first whether there is one. It is not a gate: the shared rules
in the brief judge the *host*, and a version nobody supports is a fault in the request,
which is the tool's own answer rather than something the machine did wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from basewright.profiles.model import Profile, SupportedVersion


class RequestError(ValueError):
    """The request cannot be resolved against this profile.

    Carries what was asked for and what is available, because a refusal that does not
    list the alternatives sends the reader to the profile to find them.
    """


@dataclass(frozen=True)
class Request:
    """One instance, as it was asked for.

    Frozen, and resolved once. Everything downstream reads the same request, so a rule
    and the plan it produces cannot disagree about which port was meant.
    """

    host: str
    engine: str
    version: str
    version_source: str
    environment: str
    instance: str
    port: int
    locale: str | None = None

    @property
    def chosen_version(self) -> bool:
        """Whether a person named the version, rather than taking the profile default."""
        return self.version_source == "requested"

    def document(self) -> dict[str, Any]:
        """The request as an artifact carries it."""
        document: dict[str, Any] = {
            "host": self.host,
            "engine": self.engine,
            "version": self.version,
            "version_source": self.version_source,
            "environment": self.environment,
            "instance": self.instance,
            "port": self.port,
        }
        return document

    def __str__(self) -> str:
        return f"{self.engine} {self.version}, instance {self.instance}"


def resolve_request(
    profile: Profile,
    *,
    host: str,
    version: str | None = None,
    environment: str,
    instance: str | None = None,
    port: int | None = None,
) -> Request:
    """Fill in what the request did not say, and refuse what the profile cannot do."""
    resolved_version = version or profile.default_version
    if profile.version(resolved_version) is None:
        listed = ", ".join(entry.version for entry in profile.versions)
        raise RequestError(
            f"{profile.display_name} {resolved_version} is not a version this profile "
            f"supports. It lists: {listed}. A version is chosen by a person and validated "
            f"here; it is never substituted for a nearby one."
        )

    return Request(
        host=host,
        engine=profile.engine,
        version=resolved_version,
        version_source="requested" if version else "profile_default",
        environment=environment,
        instance=instance or profile.default_instance,
        port=port if port is not None else profile.default_port,
        locale=profile.default_locale,
    )


def supported_version(profile: Profile, request: Request) -> SupportedVersion:
    """The support matrix entry for the requested version.

    Always present: :func:`resolve_request` refuses a request whose version is not in the
    matrix, so every caller after that point can rely on there being an entry.
    """
    entry = profile.version(request.version)
    if entry is None:  # pragma: no cover - resolve_request has already refused this
        raise RequestError(f"{request.version} is not in the support matrix")
    return entry
