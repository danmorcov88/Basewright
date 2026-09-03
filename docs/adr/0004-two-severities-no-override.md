# ADR-0004: Two severities, and a block is never overridable at run time

**Status:** Accepted · 2026-09-03

## Context

Preflight exists to answer one question before anything is touched: is this machine a
reasonable place to put this engine. The answers divide cleanly into two kinds. Some
findings mean the install cannot correctly proceed — the OS is not in the support matrix,
the backup path has 12 GiB free where the profile requires 100, the port is already in use.
Others mean it can proceed but somebody should know — WAL will share a mount with data,
transparent huge pages are set to `always`, the version reaches end of life in eight months.

Two pressures act on any gating system, and they pull in opposite directions.

The first is severity inflation. Given three or four levels, everything drifts toward the
middle. A finding that should stop the run gets filed as "high" rather than "fatal" because
somebody needed to get past it once, and the level that actually stops anything ends up
almost unused. The taxonomy grows and the gate weakens.

The second is the override. Every blocking check eventually meets a situation where the
person at the console is confident the check is wrong, at an hour when nobody is available
to agree. If a `--force` exists, it is used. Then it is used again, because it worked. Then
it appears in the runbook, then in a Semaphore template's default arguments, and the block
is decorative. The failure mode is not that the flag is abused by careless people; it is
that it is used correctly a few times by careful ones and then inherited by everybody else
without the context.

There is a real cost on the other side. A block that is wrong halts legitimate work, and
somebody has to wait.

## Decision

There are exactly two severities. `block` and `warn`. There is no third, and no per-rule
configuration that promotes or demotes one.

**A block produces no plan.** It produces a refusal: the rule id, the observed value, the
required value, and what would have to change. There is no partial plan, no degraded
install, and no `--force`, `--ignore-preflight`, `--skip-checks` or equivalent — at the
command line, in the inventory, in a profile, or in a Semaphore template.

**A warning does not stop planning, but it does stop applying until it is acknowledged.**
The plan renders every warning; `apply` refuses unless the caller passes
`--accept-warnings`. The acknowledgement is explicit and lands in the task log, so a warning
that was accepted is a recorded act rather than a silence.

When a block is wrong, the rule is wrong. The fix is a change to the rule in Git, where
somebody reviews it, the reasoning is recorded, and the change applies to every host rather
than to one operator's session. Where a threshold genuinely differs by host or environment,
the profile carries it as data and the inventory overrides it — which is the same mechanism,
reviewed the same way, and not an override of the outcome.

## Consequences

A refusal is a first-class, useful outcome rather than a failure of the tool. "Refused
because `/backup` has 12 GiB free and this profile requires 100 GiB" answers the question.
Installing anyway and hoping does not.

The two severities stay meaningful because there is nowhere for a finding to hide. A rule
author has to decide whether this genuinely stops the install, and there is no comfortable
middle to file it under.

Because a block cannot be bypassed at the console, the rules themselves come under real
scrutiny. A rule that fires wrongly is felt immediately and gets fixed properly. That is the
intended pressure, and it only works if fixing a rule is genuinely quick — so the threshold
data lives in the profile where a change is small and reviewable, not in the code.

The cost is bluntly stated: someone will be blocked at an inconvenient hour by a rule that
is wrong, and the answer will be a pull request rather than a flag. That is the price of the
guarantee that a block on any other host means something. The mitigation is not an escape
hatch; it is that thresholds are data, so the pull request is a one-line change to a YAML
file rather than a code change.

There is also no way to record "we know, and we accept it permanently" for a block. That is
deliberate — a permanent acceptance is a threshold change, and it should look like one.

## Rejected alternatives

**Three or more severities: info, warn, error, fatal.** More expressive, and familiar from
linters. Rejected because expressiveness is what makes severity inflation possible. With two
levels the only question is whether this stops the install; with four, the question becomes
which label to choose, and the answer trends downward under deadline pressure.

**A `--force` flag, logged loudly.** The usual compromise: allow the override, make it
conspicuous, audit it. Rejected because conspicuousness wears off. The flag migrates into
the runbook and then into template defaults, and by then the audit records that it was used,
not that anybody read the block. A gate that can be passed by typing something is a gate
whose strength is set by whoever is most tired.

**Per-rule severity overrides in the inventory.** Softer than a global flag, and targeted:
demote `disk.free_space` to a warning for this one lab environment. Rejected because it
reintroduces the override with better manners, and it makes a rule's severity depend on
where you read it from. The legitimate version of this need is a different *threshold* for
that environment, which the profile already supports as data, and which still refuses when
the host does not meet it.

**Interactive confirmation on a block.** "This host fails `disk.free_space`. Continue?"
Rejected outright. It moves the decision to the least reviewable place available — one
person, at the console, at the moment they most want to proceed — and it cannot work at all
under Semaphore, which is how this tool is meant to be run.

## Related

- [ADR-0001](0001-plan-before-apply.md) — a block means there is no plan to review.
- [ADR-0003](0003-humans-choose-the-version.md) — an unsupported version is a block; a
  near-end-of-life one is a warning.
- [ADR-0005](0005-semaphore-is-the-interface.md) — where the acknowledgement of a warning is
  recorded.
- [ADR-0010](0010-idempotency-match-or-refuse.md) — the same instinct applied to re-runs.
