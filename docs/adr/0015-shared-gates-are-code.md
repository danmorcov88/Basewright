# ADR-0015: The shared gates are code; a profile's gates are data

**Status:** Accepted · 2026-09-04

## Context

Twenty preflight rules apply to every engine. A host has to be reachable and the account
has to be able to escalate; the operating system, its version and the architecture have to
be in the support matrix; there have to be enough cores and enough memory; every path has
to be on a writable mount with enough space; the port has to be free; nothing conflicting
may already be installed; the repository has to answer; the locale has to exist. Eight more
warn rather than refuse.

Every one of those is engine-independent by construction — that is what makes them shared.
So the tempting move is obvious: write them as expressions in a file the core owns, run
them through the evaluator built in [ADR-0014](0014-rules-are-expressions-not-code.md), and
have exactly one rule mechanism in the whole tool. One code path, one report, one place to
test.

Two things get in the way, and neither is a matter of taste.

The first is what a refusal has to say. The brief is specific about it: the report names
the rule, the observed value, the required value, and what to do. *"Refused because
/backup has 2.0 GiB free and this profile requires 50GB"* is an answer somebody can act on
from the report alone. An expression returns a yes or a no. A rule written as one can
report `disk.free_space` and `false`, and the reader has to go and open the profile to find
out what the threshold was and then go to the host to find out what it actually has —
which is the work the refusal was supposed to have already done.

The second is shape. Several of the shared rules quantify over the layout rather than
asking one question: *every* path is on a writable mount, *every* path that states a
minimum has it, *every* path is on a filesystem the engine is normally run on. There is no
one-line expression for that, and the language deliberately has no comprehensions. Making
it expressible would mean adding iteration to the language — which is the point where a
small readable language starts becoming a programming one.

## Decision

**The twenty shared rules are Python functions**, in
[`basewright/preflight/shared.py`](../../basewright/preflight/shared.py). Each returns a
verdict carrying what it observed, phrased against what was required, and what would have
to change.

**A rule a profile contributes is an expression**, evaluated as ADR-0014 describes.

**Everything after that is identical.** Both kinds produce the same `GateResult`, both are
resolved against the same two severities in the same four lines, both are ordered and
rendered by the same reporter, and both appear in the artifact distinguished only by a
`source` field that says where somebody goes to argue with the rule. A report that made a
profile's rules look like second-class ones would be a report that discouraged writing
them.

**No shared rule may hold a threshold.** Every number and every name a shared rule compares
against comes from the profile: `minimums.cores` and `minimums.memory`, the
`preferences` block, the `conflicts` list, each path's `min_free` and
`prefer_separate_from`, the support matrix, the layout, the declared locale. What is
written in the core is the *question*, which is the same for every engine. The answer is
always data.

**Where a profile states no threshold, the rule reports `skip`.** It does not invent one. A
default compiled into the core would be a number nobody agreed to, applied to every engine,
and reported to the reader as though the profile had asked for it — which is worse than
saying plainly that nobody stated a floor.

One rule keeps a constant: `version.eol` warns twelve months out. That number is about how
long an organisation takes to plan a migration, not about any engine, so there is nothing
for a profile to say about it.

## Consequences

Refusals carry their arithmetic. `disk.free_space` names each path that is short, the mount
carrying it, what it has and what the profile asked for — quoted as the profile wrote it,
so `20GB` in the file reads as `20GB` in the report rather than being re-rendered as
`18.6 GiB` and sending the reader off to check whether those are the same number.

The engine-name guard still holds, and holds over the file where it matters most. Nothing
in `shared.py` names an engine, because there is nothing for it to name: it reads
`profile.minimums.cores`, not a table of engines and their minimums. `engine.not_installed`
is the sharpest test of this and it passes — the core compares reported service names
against names the profile declared as conflicts, and recognises nothing on its own.

The cost is two mechanisms where a reader might have expected one, and a boundary that has
to be explained: a rule an engine adds *about itself* is data, and a rule that refuses
hosts *for everyone* is code. It also means the twenty are changed by a pull request
against the core rather than against a profile — which is the right friction for a rule
that refuses every host in the estate, and would be the wrong friction for anything else.

There is a smaller cost in the report. A profile's failing rule can only say
`not path.data.rotational does not hold on this host`, because that is genuinely all a
boolean knows. Its `remediation` carries the weight instead, which is why the schema
requires one.

## Rejected alternatives

**The shared rules as a core-owned file of expressions.** One mechanism, one code path, and
the shared rules would be readable by the same people who read profiles. Rejected because
it delivers neither of the things the file would have to deliver: the thresholds are the
profile's, so they cannot be written in a core-owned file at all — the expressions would
have to reach into `profile.minimums`, which is fine — but the report would lose the
observed-against-required detail that is the whole value of a refusal, and three of the
rules have no single-expression form. Working around both would mean adding iteration and
a reporting vocabulary to the language, at which point it is code with extra steps.

**Shared rules as expressions, with a hand-written message per rule.** Keeps one evaluator
and restores the message. Rejected because the message would then be a format string
maintained separately from the condition it describes, and the two would drift the first
time a threshold moved. The whole point is that the thing that measured the value is the
thing that reports it.

**Let a profile override a shared rule's severity.** It would make the split invisible: a
profile could turn `disk.filesystem` into a block if it genuinely needs to. Rejected by
[ADR-0004](0004-two-severities-no-override.md), which is about run-time overrides but whose
reasoning applies here too — a rule that means different things in different profiles is a
rule whose report cannot be read across the estate. A profile that needs a stricter version
of a shared rule adds its own, with its own identifier, which is visible.

**Drop the shared rules and let every profile carry its own twenty.** Maximum consistency:
everything is data. Rejected because it guarantees twenty near-copies that diverge, and
because the second profile would be written by copying the first — which is how a
subtly-wrong threshold ends up in every engine in the estate with nobody having decided it.

## Related

- [ADR-0014](0014-rules-are-expressions-not-code.md) — the language a profile's rules are
  written in, and its limit.
- [ADR-0002](0002-engines-are-data.md) — why no shared rule may hold a threshold.
- [ADR-0004](0004-two-severities-no-override.md) — the severity resolution both kinds share.
- [ADR-0001](0001-plan-before-apply.md) — why a refusal is an artifact rather than an error.
