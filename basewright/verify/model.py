"""The observation document, and what one check came to.

An observation is what an engine's role read off a running instance. It arrives as a
document because reaching an instance runs over SSH, which is Ansible's half of the split
(ADR-0020, ADR-0024), and it is validated against a closed schema for the same reason
every other document here is: a reading the core cannot interpret is refused where it is
read rather than halfway through a judgement.

The model is deliberately thin. Unlike host facts, which are normalized into a typed model
because twenty rules read them and a fact spelled two ways would be a fact nobody could
reason about, an observation is read by exactly one judgement per kind. Giving each kind a
dataclass would be eleven classes each with one reader, so the schema is the contract and
the judgements read mappings.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from basewright.report.problems import Problem, display, render_problems
from basewright.schema import problems_in

#: The schema every observation document is read through.
OBSERVATION_SCHEMA = "observation.schema.json"


class Outcome(StrEnum):
    """What one check came to.

    Three, and the third is the one it would have been easy to leave out. A check the run
    could not put to the instance has proved nothing, and folding that into a pass would
    let a verify run exit zero having asked nothing at all (ADR-0025).
    """

    PASS = "pass"
    FAIL = "fail"
    UNOBSERVED = "unobserved"

    @property
    def verified(self) -> bool:
        """Whether this outcome leaves the instance verified. Only one of them does."""
        return self is Outcome.PASS


class ObservationError(Exception):
    """Base class for everything that stops an observation from being read."""


class MissingObservationError(ObservationError):
    """There is no observation document at that path."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"{display(path)} is not an observation document")


class InvalidObservationError(ObservationError):
    """The document is there and does not describe a reading the core can judge."""

    def __init__(self, path: Path, problems: list[Problem]) -> None:
        self.path = path
        self.problems = sorted(problems)
        super().__init__(self.report())

    def report(self) -> str:
        return render_problems(self.path, "observation document", self.problems)


@dataclass(frozen=True)
class Observation:
    """One reading of one instance, at one moment."""

    #: The plan the instance was built from. Checked against the plan being verified.
    plan_id: str
    #: The host that was read.
    host: str
    #: When it was read, in UTC.
    observed_at: datetime
    #: What was read, by kind. A kind absent from this mapping was not observed.
    observations: Mapping[str, Mapping[str, Any]]
    #: The Basewright that assembled the document, where the document says.
    tool_version: str | None = None

    def of(self, kind: str) -> Mapping[str, Any] | None:
        """The reading for one kind, or None if the run did not manage to take one."""
        return self.observations.get(kind)


def load_observation(path: Path) -> Observation:
    """Read an observation document, check it against the contract, and model it."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MissingObservationError(path) from error

    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidObservationError(
            path,
            [
                Problem(
                    file=display(path),
                    location="",
                    message=f"is not readable JSON: {error}",
                    hint=(
                        "The document is written by an engine's role, through the "
                        "basewright_observation filter. A file that is not JSON at all "
                        "usually means the role wrote a message where a document was "
                        "expected."
                    ),
                )
            ],
        ) from error

    return read_observation(document, path)


def read_observation(document: object, path: Path) -> Observation:
    """Validate a document already in memory, and model it."""
    problems = problems_in(document, schema_name=OBSERVATION_SCHEMA, file=display(path))
    if problems:
        raise InvalidObservationError(path, problems)

    # The schema is closed and required every key read below, so the document is a mapping
    # of the right shape by the time it gets here.
    validated: dict[str, Any] = document if isinstance(document, dict) else {}
    return Observation(
        plan_id=validated["plan_id"],
        host=validated["host"],
        observed_at=datetime.strptime(validated["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        ),
        observations=validated["observations"],
        tool_version=validated.get("tool_version"),
    )
