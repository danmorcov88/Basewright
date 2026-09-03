"""Validation of the plan artifact against its contract.

``plan.json`` is what apply consumes and what verify compares against, so it is the one
document in the project that two separate programs have to agree about. It is validated on
the way out of plan and on the way into apply: a contract checked only by its author is a
contract that drifts.

The schema is closed like every other, and one consequence is worth naming. A secret entry
carries a name and a location and nothing else, so there is no field in a plan a secret
value could be written into, even by mistake. The rule is structural rather than a
convention someone has to remember.
"""

from __future__ import annotations

from basewright.report.problems import Problem
from basewright.schema import problems_in

#: The schema the artifact is checked against.
PLAN_SCHEMA = "plan.schema.json"


def plan_problems(document: object) -> list[Problem]:
    """Return every way ``document`` fails to be a plan. Empty means it is one."""
    return problems_in(document, schema_name=PLAN_SCHEMA, file="plan.json")
