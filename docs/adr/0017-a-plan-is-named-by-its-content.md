# ADR-0017: A plan is named by its content

**Status:** Accepted · 2026-09-04

## Context

A plan needs a name. Semaphore's Apply template takes a plan id, so that the person who
applies a plan can be a different person from the one who produced it — that separation is
a feature, and it needs the two of them to be able to say *which* plan without ambiguity.
The name is printed in a task log, quoted in a change request, and typed into a survey
field, so it has to be short enough to read out loud.

The obvious candidates are a counter, a timestamp and a random identifier. Each of them
names the *run*. What the reader actually wants named is the *decision*: whether the plan in
front of them is the one that was approved.

That distinction has teeth. Preflight and plan are re-run constantly — after a change to a
sizing rule, after a fact is collected differently, after somebody frees up disk space, and
also for no reason at all because the person who ran it wanted to look at it again. A name
that changes on every run cannot answer *is this the same plan?*, and a name that changes
only when something meaningful changed can.

One field stands in the way of the simple version. `generated_at` differs between two runs
that decided exactly the same thing about exactly the same host, and it is the only field
that does.

## Decision

**The plan id is a digest of the plan, over the document without `generated_at`.** Twelve
hexadecimal characters of a SHA-256 over the canonical JSON — keys sorted, no whitespace —
of everything the plan says apart from when it was written.

**The document the digest is taken over never contains that field.** The plan is assembled
in two steps: a body with every section in it, and then the finished artifact with the
identity fields put in front of it. The digest is computed from the first, and
`plan_id_for` refuses a document that has `generated_at` in it rather than removing it.
Deleting a key on the way past would work identically and would be one edit away from
quietly not working; a refusal is the difference between a property and a habit.

**`tool_version` is inside the digest.** A different build of Basewright that produced a
byte-identical set of decisions still produced them differently, and the plan says so.

## Consequences

Two runs an hour apart on an unchanged host produce the same id, and the reviewer can see
at a glance that nothing was decided differently. A run after a sizing rule changed produces
a different one, which is the alarm somebody wants.

The id is a checksum as well as a name. A plan whose id does not match its own content has
been edited by hand, and apply can say so instead of executing it.

Twelve characters is a collision every few million plans within one estate, which is not a
number any estate reaches. It is short enough to read out over a call and long enough that
two plans in the same task log will not share one.

The determinism the digest depends on is a property of the whole planner, not of this
function: nothing may read a clock, iterate a set, or depend on a dictionary order that
came from anywhere but a file. That is checked separately, by rendering the goldens twice
and comparing the bytes.

`generated_at` being outside the digest means it is outside the checksum as well. Somebody
who edits that field alone produces a plan whose id still matches. That is the correct
trade: the field is documentation of a run, nothing decides on it, and protecting it would
mean giving up the property the id exists for.

## Rejected alternatives

**A random identifier, or a counter.** Trivial, guaranteed unique, and how most tools do it.
Rejected because it names the run rather than the decision, so the question *is this the
plan I approved?* has to be answered by diffing two files by hand, which nobody does.

**A timestamp.** Names the run and sorts nicely. Same objection, plus two people producing
plans in the same second.

**A digest over the whole plan, timestamp included.** One line shorter, and it makes the id
a checksum of everything. Rejected because it produces a different name for two identical
plans, which is precisely the thing this decision exists to prevent — and it would make
golden plans impossible to commit.

**Delete `generated_at` from a finished plan before digesting it.** The same result today,
in one fewer moving part. Rejected because it makes the exclusion an implementation detail
of one function rather than a property of how the document is built, and because the
failure mode is silent: a field added next to it would join the digest without anybody
deciding that it should.

**A content digest plus a sequence number, for readability.** Sortable and unique.
Rejected because the sequence needs somewhere to live, and a durable counter is a piece of
state this tool has no other reason to have.

## Related

- [ADR-0001](0001-plan-before-apply.md) — why the plan is a durable artifact at all.
- [ADR-0010](0010-idempotency-match-or-refuse.md) — apply comparing a plan against reality.
- [ADR-0016](0016-plans-carry-canonical-values.md) — what the digest is taken over.
- [ADR-0005](0005-semaphore-is-the-interface.md) — the template that takes the id.
