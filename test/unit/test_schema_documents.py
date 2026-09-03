"""The schemas themselves have to hold up, because everything else trusts them.

Three properties are checked, and each one is load-bearing rather than tidy:

* Every document is a valid JSON Schema. A schema with a typo in a keyword does not fail
  loudly -- it silently stops constraining anything, which is the worst way for a
  validation layer to break.
* Every object is closed. This is the mechanism behind the rule the architecture rests on:
  a profile that cannot introduce an unknown key cannot introduce behaviour the core would
  need a conditional for.
* Every schema describes itself, and every enumeration carries a description. An
  enumeration is where a schema encodes a decision -- there are two severities and no
  third, apply adds and modifies and never removes -- and the loader prints that
  description as the remedy when a profile violates it. A pattern is left alone: being
  told the pattern a value failed is already the answer.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from basewright.profiles.schema import PLAN_SCHEMA, PROFILE_FILES, schema_directory, schema_name_for

SCHEMA_DIR = schema_directory()

#: Keywords that close a set of permitted values. Their failure is a person meeting a
#: decision someone made, so the schema owes them the reasoning.
NEEDS_DESCRIPTION = ("enum", "const")


def schema_files() -> list[Path]:
    return sorted(SCHEMA_DIR.glob("*.schema.json"))


def load(path: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


def objects_in(schema: Any, location: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """Walk every subschema, yielding the ones that constrain an object."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield location or "(root)", schema
        for key, value in schema.items():
            if key in ("description", "title", "examples"):
                continue
            yield from objects_in(value, f"{location}.{key}" if location else key)
    elif isinstance(schema, list):
        for index, item in enumerate(schema):
            yield from objects_in(item, f"{location}[{index}]")


def enumerations_in(schema: Any, location: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """Walk every subschema that closes a set of permitted values."""
    if isinstance(schema, dict):
        if any(keyword in schema for keyword in NEEDS_DESCRIPTION):
            yield location or "(root)", schema
        for key, value in schema.items():
            yield from enumerations_in(value, f"{location}.{key}" if location else key)
    elif isinstance(schema, list):
        for index, item in enumerate(schema):
            yield from enumerations_in(item, f"{location}[{index}]")


def test_there_are_schemas_to_check() -> None:
    """A check over an empty directory is a check that always passes."""
    assert schema_files(), f"no schema documents found in {SCHEMA_DIR}"


def test_every_profile_file_has_a_schema() -> None:
    """A file of a profile with no schema is a file nothing validates."""
    for name in PROFILE_FILES:
        schema = SCHEMA_DIR / schema_name_for(name)
        assert schema.is_file(), f"{name} has no schema at {schema.name}"


def test_the_plan_artifact_has_a_schema() -> None:
    assert (SCHEMA_DIR / PLAN_SCHEMA).is_file()


@pytest.mark.parametrize("path", schema_files(), ids=lambda path: path.name)
def test_schema_is_valid(path: Path) -> None:
    Draft202012Validator.check_schema(load(path))


@pytest.mark.parametrize("path", schema_files(), ids=lambda path: path.name)
def test_schema_identifies_itself(path: Path) -> None:
    document = load(path)
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert document["$id"].endswith(path.name)
    assert document["title"]
    assert document["description"]


@pytest.mark.parametrize("path", schema_files(), ids=lambda path: path.name)
def test_every_object_is_closed(path: Path) -> None:
    """An object that accepts unknown keys is a hole in the one rule."""
    open_objects = [
        location
        for location, schema in objects_in(load(path))
        if "additionalProperties" not in schema and "propertyNames" not in schema
    ]
    assert not open_objects, (
        f"{path.name} leaves these objects open: {', '.join(open_objects)}.\n"
        "Add additionalProperties: false. A profile that can carry a key the core does "
        "not read is a profile that can imply behaviour the core does not have."
    )


@pytest.mark.parametrize("path", schema_files(), ids=lambda path: path.name)
def test_enumerations_explain_themselves(path: Path) -> None:
    """A closed set of values is a decision, and a decision owes the reader its reasoning."""
    undocumented = [
        location
        for location, schema in enumerations_in(load(path))
        if not schema.get("description")
    ]
    assert not undocumented, (
        f"{path.name} closes a set of values without saying why at: {', '.join(undocumented)}.\n"
        "The loader prints these descriptions as the remedy when a profile violates them."
    )
