"""The vocabulary a verify check's expression is evaluated against.

The second of the two vocabularies, and a separate one from
:mod:`basewright.scope` on purpose. That one describes a machine nothing has been done to
yet; this one describes an instance that exists. Sharing the names would mean
``host.memory.total_bytes`` being the machine a plan was sized against in one expression
and the machine it is running on in another, and no profile author could keep the two
apart.

Two roots. ``plan`` is what was promised, reached exactly as the artifact is written, so
an author reading plan.json can write an expression against what they see. ``observed`` is
what came back, one entry per kind.

Everything here is plain values in plain mappings, as it is next door: no object of ours
ever enters an expression, which is what makes the evaluator safe by construction rather
than by vigilance.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from basewright.expressions import UNREPORTED, base_scope
from basewright.verify.judge import JUDGEMENTS, loopback_only
from basewright.verify.model import Observation


def build_verification_scope(
    plan: Mapping[str, Any],
    observation: Observation,
) -> dict[str, Any]:
    """Everything a check's expression may read about this plan and this instance.

    A kind carries the derived answers a small expression language needs: it has no
    comprehensions on purpose, so a question about a list -- whether every socket the
    instance holds is one only this machine can reach -- is answered here rather than
    asked there.

    A kind nobody managed to observe is :data:`~basewright.expressions.UNREPORTED`, exactly
    as an uncollected fact is. Reading one is not a misspelling, and the check reports
    ``unobserved`` rather than raising.
    """
    scope = base_scope()
    scope["plan"] = plan
    scope["observed"] = {kind: _observed(kind, observation) for kind in JUDGEMENTS}
    return scope


def _observed(kind: str, observation: Observation) -> Any:
    """One kind's reading, with whatever an expression cannot work out for itself."""
    reading = observation.of(kind)
    if reading is None:
        return UNREPORTED
    if kind == "port":
        return {**reading, "loopback_only": loopback_only(reading["bound"])}
    return dict(reading)
