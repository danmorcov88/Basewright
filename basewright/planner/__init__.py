"""Sizing evaluation, layout resolution and plan assembly.

Every computed value carries the id of the rule that produced it and the explanation that
rule ships with. The plan is deterministic: identical facts and identical profiles render
byte-identical output, which is what makes a committed plan reviewable by diffing it.

A block produces no plan. There is no partial plan and no flag that makes one.
"""

from __future__ import annotations

from basewright.planner.changes import Actions, plan_actions
from basewright.planner.errors import PlanError
from basewright.planner.plan import (
    SCHEMA_VERSION,
    build_plan,
    content_of,
    plan_id_for,
    rendered,
)
from basewright.planner.schema import PLAN_SCHEMA, plan_problems
from basewright.planner.sizing import (
    Sized,
    SizingError,
    UnsizedParameterError,
    evaluate,
    evaluation_order,
)

__all__ = [
    "PLAN_SCHEMA",
    "SCHEMA_VERSION",
    "Actions",
    "PlanError",
    "Sized",
    "SizingError",
    "UnsizedParameterError",
    "build_plan",
    "content_of",
    "evaluate",
    "evaluation_order",
    "plan_actions",
    "plan_id_for",
    "plan_problems",
    "rendered",
]
