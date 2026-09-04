"""Why a plan was not produced.

A plan is refused for one of two reasons, and they are told apart because they are fixed
by different people. The profile can be wrong -- an expression that does not read, a
bound in a unit the parameter is not measured in, two rules that need each other's answer
first. Or the host can be silent: a rule reads a fact nobody collected, and there is no
value to write down.

Neither produces a partial plan. A plan missing a value is a plan apply cannot execute,
because apply consumes the plan and nothing else, and a hole in it would be discovered on
somebody else's machine halfway through.
"""

from __future__ import annotations


class PlanError(ValueError):
    """A plan that cannot be produced. Reported, never worked around."""
