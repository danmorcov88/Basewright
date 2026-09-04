"""Judging a running instance against the plan it came from.

The half of verify that decides. The other half -- reaching the instance and reading it --
is ``ansible/playbooks/verify.yml`` and an engine's role, because reaching a machine runs
over SSH and that is Ansible's side of the split (ADR-0020). Nothing in this package opens
a socket, and nothing in it knows an engine: it reads two documents, a plan and an
observation, and says whether the second is what the first promised.
"""

from __future__ import annotations

from basewright.verify.document import SCHEMA_VERSION, document
from basewright.verify.judge import JUDGEMENTS, loopback_only
from basewright.verify.model import (
    OBSERVATION_SCHEMA,
    InvalidObservationError,
    MissingObservationError,
    Observation,
    ObservationError,
    Outcome,
    load_observation,
    read_observation,
)
from basewright.verify.run import CheckResult, VerifyError, VerifyResult, verify

__all__ = [
    "JUDGEMENTS",
    "OBSERVATION_SCHEMA",
    "SCHEMA_VERSION",
    "CheckResult",
    "InvalidObservationError",
    "MissingObservationError",
    "Observation",
    "ObservationError",
    "Outcome",
    "VerifyError",
    "VerifyResult",
    "document",
    "load_observation",
    "loopback_only",
    "read_observation",
    "verify",
]
