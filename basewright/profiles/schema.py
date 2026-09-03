"""The schema documents, and the translation of a schema violation into a remedy.

The seven files of a profile and the plan artifact each have a JSON Schema, and every
object in every one of them is closed. That is the mechanism behind the rule this project
rests on: a profile cannot introduce a key the core does not already understand, so it
cannot introduce behaviour the core would have to grow a conditional for.

Schemas live in ``schema/`` at the repository root, where they are reviewable next to the
profiles they describe, and are copied into the wheel so an installed Basewright validates
without a checkout.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from basewright.profiles.errors import ProfileProblem

#: The files a profile is made of, in the order they are read and reported.
PROFILE_FILES: tuple[str, ...] = (
    "profile.yml",
    "support-matrix.yml",
    "requirements.yml",
    "layout.yml",
    "sizing.yml",
    "packages.yml",
    "verify.yml",
)

#: The schema for the plan artifact. Not part of a profile; validated by the same code.
PLAN_SCHEMA = "plan.schema.json"

#: Where the schemas are looked for, in order. The first is the copy inside an installed
#: wheel; the second is the repository, which is what a development checkout has.
_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "_schema",
    Path(__file__).resolve().parents[2] / "schema",
)

#: Remedies for the keywords whose failure the schema itself cannot usefully explain.
_GENERIC_HINTS: dict[str, str] = {
    "additionalProperties": (
        "The schema is closed, so this key is either a typo or behaviour the core does "
        "not implement. If the core genuinely needs it, extend the schema rather than "
        "letting a profile smuggle it in."
    ),
    "minItems": "The list has to carry at least one entry to mean anything.",
    "minProperties": "The mapping has to carry at least one entry to mean anything.",
    "uniqueItems": "The same entry appears twice.",
}


def schema_directory() -> Path:
    """Return the directory holding the schema documents."""
    for candidate in _CANDIDATES:
        if candidate.is_dir():
            return candidate
    looked = ", ".join(candidate.as_posix() for candidate in _CANDIDATES)
    raise FileNotFoundError(f"no schema directory found; looked in: {looked}")


def schema_name_for(profile_file: str) -> str:
    """Return the schema document that describes one file of a profile."""
    return profile_file.replace(".yml", ".schema.json")


@cache
def load_schema(name: str) -> dict[str, Any]:
    """Read one schema document. Cached: the schemas do not change during a run."""
    document: dict[str, Any] = json.loads((schema_directory() / name).read_text(encoding="utf-8"))
    return document


@cache
def validator_for(name: str) -> Draft202012Validator:
    """Return a validator for one schema document."""
    return Draft202012Validator(load_schema(name))


def problems_in(document: object, *, schema_name: str, file: str) -> list[ProfileProblem]:
    """Validate a document and return every violation as an actionable problem."""
    found: list[ProfileProblem] = []
    for error in validator_for(schema_name).iter_errors(document):
        found.extend(_problems_from(error, file))
    return sorted(set(found))


def _problems_from(error: ValidationError, file: str) -> Iterator[ProfileProblem]:
    """Translate one validation error into one problem per thing a person has to fix.

    A ``required`` or ``additionalProperties`` failure is reported by the validator
    against the containing object. Reporting it against the key itself is what makes the
    location in the message the place the editor's cursor goes.
    """
    location = _location(error.absolute_path)

    if error.validator == "required" and isinstance(error.instance, dict):
        for name in _missing(error):
            yield ProfileProblem(
                file=file,
                location=_join(location, name),
                message="is required but missing",
                hint=_described(error.schema, name),
            )
        return

    if error.validator == "additionalProperties" and isinstance(error.instance, dict):
        defined = _properties(error.schema)
        for name in sorted(key for key in error.instance if key not in defined):
            allowed = ", ".join(sorted(defined))
            yield ProfileProblem(
                file=file,
                location=_join(location, name),
                message="is not a key this schema defines",
                hint=f"{_GENERIC_HINTS['additionalProperties']} Keys here are: {allowed}.",
            )
        return

    yield ProfileProblem(
        file=file,
        location=location,
        message=_message(error),
        hint=_hint(error),
    )


def _missing(error: ValidationError) -> list[str]:
    """The required keys the instance does not carry."""
    required = error.validator_value if isinstance(error.validator_value, list) else []
    instance = error.instance if isinstance(error.instance, dict) else {}
    return sorted(str(name) for name in required if name not in instance)


def _properties(schema: object) -> dict[str, Any]:
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            return properties
    return {}


def _described(schema: object, name: str) -> str:
    """The schema's own description of a missing key, used as the remedy.

    A key described by the schema explains itself. Where the schema describes the
    containing object instead -- which is what a mapping of open-ended keys looks like --
    that description is the next best answer to "what was this for".
    """
    property_schema = _properties(schema).get(name)
    for candidate in (property_schema, schema):
        if isinstance(candidate, dict):
            description = candidate.get("description")
            if isinstance(description, str):
                return description
    return ""


def _message(error: ValidationError) -> str:
    """Restate the failure as something the reader can act on."""
    value = error.instance
    if error.validator == "enum" and isinstance(error.validator_value, list):
        allowed = ", ".join(str(option) for option in error.validator_value)
        return f"{value!r} is not one of: {allowed}"
    if error.validator == "const":
        return f"{value!r} is not {error.validator_value!r}"
    if error.validator == "pattern":
        return f"{value!r} does not match {error.validator_value}"
    if error.validator == "type":
        expected: object = error.validator_value
        if isinstance(expected, str):
            return f"{value!r} is not of type {expected}"
        if isinstance(expected, list):
            wanted = " or ".join(str(option) for option in expected)
            return f"{value!r} is not of type {wanted}"
    return error.message


def _hint(error: ValidationError) -> str:
    """A remedy: the schema's own description, or a stock explanation of the keyword."""
    if isinstance(error.schema, dict):
        description = error.schema.get("description")
        if isinstance(description, str):
            return description
    return _GENERIC_HINTS.get(str(error.validator), "")


def _location(path: Iterable[str | int]) -> str:
    """Render a path into a document the way a person would write it: ``rules[0].expr``."""
    rendered = ""
    for part in path:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered = f"{rendered}.{part}" if rendered else str(part)
    return rendered


def _join(location: str, name: str) -> str:
    return f"{location}.{name}" if location else name
