# ADR-0010: A re-run either matches or refuses, and never surprises

**Status:** Accepted · 2026-09-03

## Context

`apply` will be run more than once against the same host. Sometimes deliberately — a task
was retried after a network failure, or a plan was re-applied to confirm nothing drifted.
Sometimes not — the same Semaphore template was launched twice, or a plan from last month was
applied to a host that has moved on since.

Idempotency in the ordinary configuration-management sense covers the easy case: running the
same role twice converges, and the second run reports no changes. That is necessary and not
sufficient here, because this tool applies a plan that was computed from a *snapshot* of the
host. The facts underneath a plan can go stale. Memory can be resized. A disk can fill. A
mount can be added, so a path that was on one filesystem is now on another. Someone can
install a conflicting instance by hand.

Applying a plan built from facts that no longer hold is the dangerous case, and it does not
announce itself. The role's tasks each behave correctly and the run exits zero, and the
result is an instance sized for a machine that no longer exists — 8 GB of `shared_buffers`
on a host that was downsized to 8 GiB of RAM.

There is a second, quieter failure. Basewright creates and configures; it must not destroy.
A re-run that helpfully overwrites a config file somebody hand-edited between runs has
silently discarded a change, and the operator finds out from a behaviour difference rather
than from the tool.

## Decision

A re-run has exactly two acceptable outcomes: it matches, or it refuses. There is no third
outcome in which it adapts.

**Roles are idempotent.** A second run against an unchanged host with the same plan reports
no changes. Molecule scenarios assert this, so a role that stopped being idempotent fails CI
rather than being noticed in production.

**`apply` re-verifies its own premises before acting.** The plan carries the facts it was
derived from. `apply` re-gathers and compares. If the host has changed materially — the
things the plan's decisions actually depended on — it refuses and asks for a fresh plan. It
does not re-derive values, because re-deriving would mean applying something nobody reviewed
([ADR-0001](0001-plan-before-apply.md)).

Which differences count as material is profile data, not a judgement made at run time. A
kernel patch level moving does not invalidate a plan; total memory changing does.

**Nothing is destroyed.** `apply` creates and configures. It does not drop a data directory,
remove an existing instance, or overwrite an existing config file without leaving a
timestamped copy beside it — `postgresql.conf.basewright.2026-09-03T10-14-22`. A conflicting
existing instance is a preflight block (`engine.not_installed`), not something to clear out
of the way.

**A refusal is a first-class outcome.** It names what changed, what the plan assumed, and
what to do — produce a new plan. It is not an error state to be retried past.

## Consequences

A stale plan cannot quietly produce a wrong instance. The failure mode moves from "silently
sized for the wrong machine" to "refused, with the two values printed side by side", which is
the whole thesis of the project applied to its own second run.

Re-running becomes safe enough to be routine. `apply` can be used to confirm a host still
matches its plan, and `verify` can be run months later on its own, because neither will
improvise.

The no-destruction rule means Basewright can be pointed at a host without the operator
first having to reason about what it might remove. The cost is a slow accumulation of
timestamped backup files on hosts that are reconfigured often, which is a housekeeping
problem and a good trade against the alternative.

The costs. `apply` gathers facts before it acts, so it is slower than a straight role run.
An operator who genuinely wants the new values has an extra step — re-plan, review, apply —
and that step will feel like ceremony when the change is small and obvious. It is kept
because "small and obvious" is a judgement made by the person in a hurry.

Defining materiality is a design obligation that will be got wrong at first: too broad and
plans expire pointlessly, too narrow and a real change slips through. Being profile data
means it is adjustable in a reviewed change rather than in code.

## Rejected alternatives

**Re-derive values at apply time when the facts have moved.** The helpful behaviour: notice
the host changed, recompute, carry on. Rejected because it applies something nobody
reviewed, which defeats the plan artifact entirely. It also means the same command produces
different results on different days without saying so.

**Apply the plan regardless and let verify catch the mismatch.** Simpler, and `verify`
exists precisely to compare a live instance against its plan. Rejected because it catches the
problem after the change, on a host that is now misconfigured, when the same information was
available beforehand. Preflight-style gating before a change is the pattern this whole tool
is built on; abandoning it for apply's own preconditions would be inconsistent.

**A `--force` to apply a plan against drifted facts.** The familiar escape hatch. Rejected
for the reasons in [ADR-0004](0004-two-severities-no-override.md): it would be used, then
inherited, then defaulted, and the check would be decorative. Producing a fresh plan is
cheap — it changes no host — so there is no case where forcing is the only option.

**Overwrite configuration files without keeping a copy.** Cleaner hosts, no backup litter,
and arguably correct since the plan is the source of truth. Rejected because a hand-edit
between runs is usually somebody solving a real problem under pressure, and discarding it
silently converts a small process failure into an outage nobody can explain.

## Related

- [ADR-0001](0001-plan-before-apply.md) — why apply must not re-derive.
- [ADR-0004](0004-two-severities-no-override.md) — the same refusal instinct at the gate.
- [ADR-0008](0008-python-decides-ansible-acts.md) — why a role cannot adapt on its own.
