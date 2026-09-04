# ADR-0023: Drift is measured against the plan, and free space is not part of it

**Status:** Accepted · 2026-09-04

## Context

§9 of the brief asks that a re-run against a drifted host produce a diff first: apply
re-verifies that the host still matches the facts the plan was built from, and refuses if
it has changed materially. The reasoning is obvious once stated — a plan is a set of
decisions about a machine as it was at one moment, and apply runs later, sometimes a
fortnight later after somebody approved it.

Two things make it harder than it looks.

**What apply can compare is exactly what the plan wrote down.** Apply reads the plan and
nothing else, so the comparison is against `plan.host`, which is a subset of the facts.
It carries the operating system, the architecture, the processor count, the memory, the
filesystems and the clock. It does not carry the services installed, the ports something is
listening on, the locales, the kernel settings or the firewall — those were read by gates
before the plan existed and were not recorded in it.

**Deciding which differences matter is the whole problem.** A check that refuses on any
difference refuses every second run and gets turned off within a month. One that refuses on
none of them is decoration. Between those, every candidate rule has a failure mode: a
kernel version changes at every patch window; free space changes while you are looking at
it; memory can genuinely be taken away from a virtual machine between the plan and the
apply.

## Decision

**Facts are compared in two ways, according to what kind of fact they are.**

*Identity* — the operating system family, distribution and version, the architecture, and
per filesystem its type and whether it spins. Every one of these was read by a rule that
reached a verdict or computed a value, and a change to any of them means this is a different
machine. These must match exactly.

*Capacity* — the processor count and the total memory. These drift when they **shrink** and
not when they grow. Applying a plan sized for a larger machine onto a smaller one is the
failure this exists to catch; a host that has been given more memory is still one this plan
fits, and refusing it would be refusing an improvement.

**A filesystem the plan placed a path on and the host no longer reports is drift**, and it
is the loudest of them: a path created on a filesystem that is not mounted lands on whatever
covers the directory instead, which is how a data directory ends up on the root volume.

**Free space is not compared at all.** It is a capacity fact, a blocking rule reads it, and
it looks like the first thing this should catch. It is left out because **apply consumes
it**: installing the packages and creating the instance is exactly what makes a filesystem
smaller, so a second run comparing against the numbers in the plan would report its own work
as drift and refuse to be idempotent — breaking the more important promise to keep the less
important one. Answering it properly means asking whether the host still clears the floor
the profile requires, and that floor is in the profile, which apply does not read. So it is
checked once, by a blocking gate, before the plan exists.

**What is not checked is written down in the code rather than left to be discovered.**
`UNCHECKED` in `basewright/drift.py` names each limit and why it is one, and a test asserts
it is not empty. A drift check is only as wide as the record it compares against, and
somebody relying on it is entitled to know where it stops looking.

**The comparison is a pure function under pytest, reached from Ansible through a filter.**
It takes the plan's host section and one built from facts collected moments earlier, by the
same collecting role and the same document function the whole project uses — so there is one
definition of what a plan records about a machine, and drift reads it rather than a second,
slightly different view of the same host.

**The facts for it are collected without being written down.** A collected document records
the moment it was collected, so writing one on every apply would report a change on every
run of the one step whose promise is that a second run changes nothing. The collecting role
gained an option for this, and the answer still goes through the same filter its own
template uses.

## Consequences

Apply refuses a host that has been rebuilt, resized downward, or had a filesystem go away,
and it refuses before it has touched anything. That is most of the value, and it is the part
that would otherwise be discovered as an instance sized for hardware it is not running on.

Apply does **not** notice an engine somebody else installed since the plan was made, or a
port taken since. Both are real gaps and both are consequences of the plan being a subset
rather than of the check being weak. They are found later and less kindly: the packaging
refuses, or the service fails to bind. Widening the plan's host section to close them is a
version of the contract, and it is not obviously worth one — those two rules exist to stop a
host reaching a plan at all, and a host that acquires a conflicting instance between plan and
apply is a rarer event than the ones above.

A host given more memory or more cores between the plan and the apply is applied to without
comment, and the instance is sized for the smaller machine it was planned for. That is the
right behaviour — the plan is what was approved — but it means the plan should be produced
again after a resize, and nothing here says so out loud.

The two-way split is a judgement, and it is one somebody may argue with. It is written in
one table per kind, in one module, with the reasoning beside each entry, so arguing with it
means changing a line rather than reading a function.

## Rejected alternatives

**Compare every field of the host section and refuse on any difference.** The obvious
implementation, and the one that needs no judgement. Rejected because it refuses after every
patch window: the kernel version, the pretty name of a point release and the free space on
every filesystem all move on their own. A check that cries wolf is a check somebody adds a
flag to turn off, and there is no flag in this project to add.

**Re-run preflight against the current facts and compare the verdicts to the ones in the
plan.** By far the most elegant answer: it needs no table of material fields, and it
expresses drift in exactly the vocabulary the project already has — a rule that passed and
now blocks. Rejected because preflight needs the profile, and apply must not read one. Worse,
it would make the verdict depend on the profile *as it is now*, so editing a threshold in Git
would change whether a months-old plan may be applied — which is precisely the coupling the
frozen plan exists to prevent.

**Compare free space with a tolerance.** A percentage, or a fixed margin, and drift only
below it. Rejected because the number would be invented. Every threshold in this project is
declared in a profile by somebody willing to defend it in review, and a tolerance in the core
would be the one threshold nobody had argued for.

**Widen `plan.host` so drift can see services and ports.** It would close the two real gaps.
Rejected for now rather than on principle: it is a version of the contract, and the contract
had just moved for something apply could not run without. This is a gap in what apply
notices, not a gap in what apply can do, and it deserves its own argument rather than being
carried along.

**Have the drift check write its facts document like every other collection.** One code
path, one artifact, and a record of what the host was at apply time -- which is genuinely
useful. Rejected because a document records the moment it was collected, so writing one
would make every apply report a change and the idempotence check meaningless. An audit trail
of what a host was when it was applied to is Phase E, and it needs a place to keep documents
rather than a file beside the checkout.

## Related

- [ADR-0022](0022-the-plan-says-how-the-instance-is-created.md) — the contract this reads,
  and why apply may read nothing else.
- [ADR-0010](0010-idempotency-match-or-refuse.md) — a re-run either matches or refuses, which
  is what this is the "refuses" half of.
- [ADR-0020](0020-the-playbook-is-the-entry-point.md) — the collecting arrangement the facts
  for this come from.
- [ADR-0001](0001-plan-before-apply.md) — why the plan is the thing being compared against.
