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
)
from basewright.profiles.loader import load_profile, load_profiles, profile_directories
from basewright.profiles.locate import (
    UnknownEngineError,
    directory_for,
    known_engines,
    profiles_directory,
)
from basewright.profiles.model import (
    GateRule,
    Initialization,
    InitializationSetting,
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
from basewright.profiles.schema import PROFILE_FILES
from basewright.report.problems import Problem
from basewright.schema import schema_directory

__all__ = [
    "PROFILE_FILES",
    "GateRule",
    "Initialization",
    "InitializationSetting",
    "InvalidProfileError",
    "MissingProfileError",
    "PackageSet",
    "PathSpec",
    "Problem",
    "Profile",
    "ProfileError",
    "Repository",
    "ServiceAccount",
    "SizingRule",
    "SupportedOS",
    "SupportedVersion",
    "UnknownEngineError",
    "VerifyCheck",
    "directory_for",
    "known_engines",
    "load_profile",
    "load_profiles",
    "profile_directories",
    "profiles_directory",
    "schema_directory",
]
