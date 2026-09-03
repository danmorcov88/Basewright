# ADR-0009: Sizing rules are declarative and carry their own explanation

**Status:** Accepted · 2026-09-03

## Context

The values in a tuned database configuration are the accumulated judgement of the people who
set them. `shared_buffers` at a quarter of RAM, capped; `random_page_cost` lowered on SSD;
`work_mem` divided down because a query can open several sort nodes at once. Each of those
is a defensible position with a reason behind it.

The reason is what goes missing. A config file holds the number and not the argument, so six
months later the number is either treated as sacred or changed by someone who does not know
what it was protecting against. Both failures are common and both are expensive.

Where the reasoning is written down at all, it is usually in a runbook or a wiki page beside
the code that computes the value. Two artifacts, updated by different people at different
times, drifting apart from the first change onward. A comment in a Jinja template is closer
to the code but invisible in the output, so it helps whoever maintains the template and
nobody who reads the result.

There is also the review problem. The people best placed to argue about whether
`maintenance_work_mem` should be capped at 2 GB are DBAs. If that decision lives inside a
Python function or a chain of Jinja filters, they cannot review it, and the tuning ends up
owned by whoever is comfortable with the code rather than whoever knows the engine.

## Decision

Sizing is a list of declarative rules in `profiles/<engine>/sizing.yml`. Each rule carries an
id, the parameter it sets, an expression over host facts, optional bounds, and a `why`.

```yaml
- id: pg.shared_buffers
  parameter: shared_buffers
  expr: "0.25 * mem_total"
  min: "128MB"
  max: "8GB"
  why: "25% of RAM is the standard starting point; capped at 8GB because beyond that
        the OS page cache is the better place for the memory."
```

**The `why` is mandatory and it is rendered into the plan, next to the computed value.** It
is not a comment. It is output. Somebody reading a plan sees the number and the argument for
it in the same place, without leaving the artifact.

The expression is evaluated by the planner over normalised facts, not by a template engine
([ADR-0008](0008-python-decides-ansible-acts.md)). Bounds are applied by the core, so
clamping behaves identically for every rule and every engine, and the plan can say when a
bound was the thing that actually decided the value.

Every rule ships with a golden fixture. A change to a rule therefore appears in the pull
request as a before-and-after of the rendered plan — the diff is the review mechanism, and
it is more useful than any single assertion about the number.

A `why` that restates the expression is not a `why`. "Sets shared_buffers to 25% of memory"
explains nothing; the expression already said that. The question it has to answer is why a
quarter, and why the cap.

## Consequences

The plan answers "why is this value what it is" at the point of asking, for every value, on
every host. That was the original complaint, and this is the mechanism that addresses it.

Tuning becomes reviewable by the people qualified to review it. A change to
`profiles/postgresql/sizing.yml` is a YAML diff plus a rendered-plan diff — readable by a
DBA, arguable by a DBA, and mergeable without touching the core.

Because bounds are core behaviour rather than per-rule arithmetic, clamping is consistent
and testable once. The plan can distinguish a value that came out of the expression from one
the cap decided, which is exactly the case where the reason matters most.

The costs. Writing a real `why` is harder than writing the number, and the rule is
unenforceable by machine — CI can require the field to be present and non-empty, but only a
reviewer can reject "sensible default". That makes it a review obligation that has to be
held, and it will be tempting to wave through on a busy day.

The expression language is a real design surface. It must be expressive enough for the rules
engines actually need — arithmetic, comparison, conditional selection over facts — and
narrow enough to be safe and comprehensible. It will not stretch to every case, and the
answer when it does not is to extend it deliberately for everyone rather than to add an
escape hatch for one profile ([ADR-0002](0002-engines-are-data.md)).

A `why` also has a shelf life. "Capped at 8GB because the OS page cache is better placed for
the memory" is a statement about how the engine behaves today, and engines change. A stale
justification is more dangerous than none, because it is believed.

## Rejected alternatives

**Sizing in Python functions, with docstrings for the reasoning.** Full expressiveness, real
tests, no expression language to design. Rejected because the reasoning stays in the source
and never reaches the plan, and because tuning would then be a code change — closing it off
to the reviewers who should own it.

**Values in YAML with the explanation in a separate document.** The conventional split:
data here, prose there. Rejected because the two drift from the first change, and because
the explanation is not present at the moment of reading the value, which is the only moment
it matters.

**A `why` as an optional field, encouraged but not required.** Lower friction, and most
rules would have one. Rejected because the rules that would skip it are the ones written in a
hurry, which correlate with the ones whose reasoning is least obvious. Optional documentation
is documentation for the easy cases.

**Auto-generating explanations from the expression and the facts.** "25% of 32 GiB, capped
at 8 GB" can be produced mechanically, and it is genuinely useful. Rejected as a
*replacement* because it describes the computation rather than the judgement — it can say
what happened but never why a quarter. It is kept as an addition: the plan shows both the
derivation and the author's reason.

## Related

- [ADR-0001](0001-plan-before-apply.md) — where the explanation is rendered.
- [ADR-0002](0002-engines-are-data.md) — why the rules are profile data.
- [ADR-0008](0008-python-decides-ansible-acts.md) — what evaluates the expressions.
