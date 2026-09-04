# ADR-0025: A check nobody could run is not a pass, and it refuses the run

**Status:** Accepted · 2026-09-04

## Context

A verify check has an obvious two outcomes: the instance is what the plan said, or it is
not. There is a third, and whether it exists at all is a decision rather than an oversight.

An engine's role puts eleven questions to a running instance. Some of them it may not
manage to put. A cluster that is down cannot be asked about its parameters, its paths, its
authentication rules or its accounts — one root cause, seven questions unanswered. A
profile can name a kind the plan makes no promise about. A reading can come back missing a
parameter the plan sizes.

The gate engine already met this and answered it. A rule that reads a fact the host did not
report is `skip`: not a pass, not a block, reported as its own outcome and counted
separately. The tempting move is to do the same here and stop thinking about it.

It is the wrong move, and the reason is what the two steps are for.

**Preflight is asked before anything has been done.** It decides whether a host can carry
an instance. A rule about a fact nobody collected is not a reason to refuse a host — the
host may be perfectly fit and the collector simply did not ask — so skipping is right, and
skipping does not stop the run.

**Verify is asked afterwards, and what it produces is a claim.** The claim is that this
instance is what its plan describes. A check nobody managed to run has contributed nothing
to that claim. Treating it as a pass would let a run that asked almost nothing exit zero,
and the report it produced would be indistinguishable from a run that asked everything —
which is exactly the failure the whole project exists to end, moved one step later. A
provisioning job that exits zero tells you a package was installed; a verify that exits
zero having asked nothing tells you even less, while looking like proof.

## Decision

**There are three outcomes: `pass`, `fail` and `unobserved`. A run with any `unobserved`
does not verify the instance, and exits 2 exactly as a failing one does.**

A check is `unobserved` when the observation document carries no reading for its kind, when
the plan carries no promise for it to be judged against, or when the reading is there and
does not cover what the check needs — a parameter the plan sizes and the instance was not
asked about.

**`unobserved` is kept apart from `fail` because what somebody does about it differs.** A
failure says the instance is wrong and the report names what to change. An unobserved check
says nobody managed to ask, and what to do is find out why the question could not be put.
Folding them together would lose that, and the report is read by somebody who has to act on
it within the hour.

**The verdict says which of the two happened.** A run with failures reads `FAILED` and
names them. A run with none and something unobserved reads `UNPROVED`: nothing contradicts
the plan, and this run did not verify the instance. Those are different sentences because
they are different situations, and a reader who is told the second one when the first is
true would go looking in the wrong place.

**A root cause stays visible.** A cluster that is down produces one `fail` — the service —
and seven `unobserved`, rather than eight identical failures. The report names the one
thing to fix.

**There is no flag.** Consistent with there being no flag that turns a block into a warning
([ADR-0004](0004-two-severities-no-override.md)): if a check cannot be run on an
instance that is genuinely correct, the check is wrong, and it gets fixed in Git.

## Consequences

- A verify run is a claim about eleven checks or it is not a claim. There is no partial
  proof that reports as success.
- Semaphore marks the task red on an unproved run, which is right: somebody has to look.
  What they read is a verdict that tells them the instance may well be fine and the run did
  not establish it.
- A profile that names a kind its engine's role cannot observe finds out on the first run,
  loudly, rather than by having that check silently never run. This is the property that
  matters most as a second engine arrives.
- The summary line carries three counts rather than two, and `verify.json` carries the same
  three. A consumer counting only failures would read an unproved run as a good one, so the
  contract makes it awkward to.

## Rejected alternatives

**Fold it into `fail`.** Simpler, one fewer outcome, and the exit code would be the same.
It reports "this instance is wrong" about an instance nobody managed to look at, which is a
different and possibly false statement — and it would put a cluster that is down at the top
of a report with eight failures, seven of them consequences of the first.

**Fold it into `pass`, as `skip` effectively does in preflight.** The reason the gate engine
does that does not transfer: preflight is deciding whether to proceed, and verify is making
a claim. This is the alternative that would let a verify run prove nothing and say so in
green.

**Report it, and let it not affect the exit code.** The middle position, and the one that
sounds reasonable: the report is honest, and only a real mismatch turns the task red. It
fails on the case that matters — an instance nobody could reach at all would exit zero, and
Semaphore would show a green task next to a database that may not exist. Anything a person
has to read the report to discover is something they will eventually not read.
