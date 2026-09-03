# ADR-0001: Plan before apply, and the plan is a durable artifact

**Status:** Accepted · 2026-09-03

## Context

The work this tool replaces is manual. Someone logs into a new machine, looks at what it
has, decides which engine version fits, picks values for a dozen parameters, and installs.
The decisions are real and often good. They are also invisible: they exist in the operator's
head during the session and nowhere afterwards.

The cost shows up later, not during the install. Six months on, somebody asks why
`shared_buffers` is 8 GB on one host and 4 GB on its twin. The answer is not written down
anywhere, so it is reconstructed from shell history, from the config file itself, or from
whoever happens to remember. A second person cannot review a decision that was never
recorded, and a change advisory board cannot approve one.

Configuration management tools do not solve this by themselves. A playbook run that exits
zero says a task converged. It does not say what values it converged on, why those values,
or whether the machine was a sensible place to put this engine at all. The reasoning is
distributed across templates, variable precedence and conditionals, which is a poor place to
read it from.

## Decision

`plan` is a separate step that runs before `apply`, produces no change on the target, and
writes a file.

The plan contains the complete intended end state: the resolved engine version, every
filesystem path with its mode and owner, every parameter with its computed value, the id of
the rule that produced that value, and the explanation that rule carries. It also contains
the facts it was derived from and the list of changes `apply` would make.

The plan is written in two forms from one model: `plan.json`, which `apply` and `verify`
both consume, and a console rendering for the person who has to approve it.

Three properties are required of it:

- **Deterministic.** The same facts and the same profiles produce byte-identical output.
- **Versioned.** It carries the tool version and the profile version, and `apply` refuses a
  plan produced by a different major version.
- **Safe to share.** It contains no secret, because it is the artifact people attach to
  change requests. See [ADR-0007](0007-secrets-never-in-artifacts.md).

`apply` consumes `plan.json` and nothing else. It does not re-derive a value, and it does
not fall back to a default when the plan is silent. If `apply` needs something the plan does
not carry, the plan is incomplete and the plan step is what gets fixed.

## Consequences

A decision becomes a reviewable object. It can be read by a second person, committed to
Git, attached to a change request, and diffed against the plan from three months ago. The
question "why is this value what it is" has a file to answer it.

Determinism buys the testing strategy. Because the same fixtures always render the same
bytes, a directory of fixture hosts with committed expected plans becomes the review
mechanism for tuning decisions: changing a sizing rule shows up in the pull request as a
readable before-and-after of the rendered plan, which is more useful than any assertion
about the number itself.

The separation also separates the people. The person who produces a plan need not be the
person who applies it, which is a feature in an environment with change control.

The cost is a two-step workflow where a one-step one would do, and a real constraint on the
implementation: any value `apply` needs has to be in the plan, so a value that is convenient
to compute at apply time must be pulled forward into the planner instead. That constraint is
load-bearing rather than incidental — it is what stops reasoning from leaking back into the
execution layer, which is where it was invisible before.

Plans also have to live somewhere durable enough to be retrieved by id later, which is
storage this tool would not otherwise need.

## Rejected alternatives

**A dry-run flag on apply.** The usual shape: `--check`, which walks the same code path and
prints what it would do. Rejected because a dry run reports *tasks*, not *decisions*. It
tells you a template would be written; it does not tell you `work_mem` came out at 10 MB
because a quarter of the memory was divided across twice the connection limit. It also
leaves nothing behind — there is no artifact to attach, review or diff, and no way to apply
in an hour exactly what was reviewed this morning.

**Deriving values at apply time from the same rules.** Simpler, one step, no artifact to
keep in sync. Rejected because the facts can move between the review and the run. If apply
re-derives, then what was approved and what was applied are two different things that merely
usually agree. Freezing the values in the plan and having apply verify the host still
matches the facts underneath it is the version of this that fails loudly rather than
silently.

**A plan in prose, generated for humans only.** Cheaper to produce and pleasant to read.
Rejected because `verify` needs a machine-readable contract to compare a live instance
against, and maintaining a separate human document alongside it guarantees the two drift.
One model, rendered twice, cannot.

## Related

- [ADR-0004](0004-two-severities-no-override.md) — a block produces a refusal, never a
  partial plan.
- [ADR-0008](0008-python-decides-ansible-acts.md) — the plan is the boundary between the
  part that decides and the part that acts.
- [ADR-0009](0009-sizing-rules-explain-themselves.md) — where the explanation next to each
  value comes from.
- [ADR-0010](0010-idempotency-match-or-refuse.md) — what happens when a plan meets a host
  that has drifted.
