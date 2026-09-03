"""The gate engine: evaluates preflight rules against facts and a request.

Rules carry an id, a severity and a remediation string. Severity is either
``block`` or ``warn``; there is no third level and no run-time override. A block
produces a refusal, never a partial plan.
"""
