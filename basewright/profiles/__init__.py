"""Loading and schema validation of profiles.

A profile is a directory of declarative files describing one database engine. The loader
validates it against the JSON Schema in ``schema/`` and rejects unknown keys, so a profile
cannot smuggle in behaviour the core does not understand.

The profile is also the only shape in which the core ever meets an engine. Nothing above
this package knows that engines differ; it reads rules, versions, paths and package names
from a :class:`Profile` and treats them all alike.
"""

from __future__ import annotations

from basewright.profiles.errors import (
    InvalidProfileError,
    MissingProfileError,
    ProfileError,
    ProfileProblem,
)
from basewright.profiles.loader import load_profile, load_profiles, profile_directories
from basewright.profiles.model import (
    GateRule,
    PackageSet,
    PathSpec,
    Profile,
    Repository,
    ServiceAccount,
    SizingRule,
    SupportedOS,
    SupportedVersion,
    VerifyCheck,
)
from basewright.profiles.schema import PROFILE_FILES, schema_directory

__all__ = [
    "PROFILE_FILES",
    "GateRule",
    "InvalidProfileError",
    "MissingProfileError",
    "PackageSet",
    "PathSpec",
    "Profile",
    "ProfileError",
    "ProfileProblem",
    "Repository",
    "ServiceAccount",
    "SizingRule",
    "SupportedOS",
    "SupportedVersion",
    "VerifyCheck",
    "load_profile",
    "load_profiles",
    "profile_directories",
    "schema_directory",
]
