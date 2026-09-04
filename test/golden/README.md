# Golden plans

One fixture host, put through the whole pipeline against one profile, with the answer
committed. `plan/` holds the plans of the hosts that can carry an instance; `refused/`
holds the reports of the hosts that cannot.

## Why they are here

A sizing rule is a decision about somebody else's production database. The way to review
such a decision is to read the difference it makes to a plan, not to read the arithmetic
and imagine one. So a change to a rule shows up in a pull request as a diff of the values
it produced, on five real machines, and a reviewer who has never seen the evaluator can
still tell whether the change was the one that was meant.

The refusals are here for the same reason in reverse. A change that quietly stops refusing
a host is the change most worth noticing, and it is invisible in a suite that only checks
the hosts that pass.

## Regenerating them

```
python tools/render_goldens.py            # write them
python tools/render_goldens.py --check    # what CI runs
make golden                               # the same, spelled shorter
```

Read the diff before committing it. A golden that is regenerated but not read is a test
that agrees with whatever the code does, which is no test at all.

## What is pinned, and what is not

`generated_at` is fixed to one moment, and every rule that reads the calendar is evaluated
against that same date. It is the one field two otherwise identical plans legitimately
differ in, and it is excluded from the plan id for the same reason.

Nothing else is pinned. `tool_version` is real, so a release moves one line in each plan
and nobody has to wonder whether the artifact still records which tool produced it.

## What they are not

They are not a substitute for unit tests. A golden shows what the pipeline decided; it
does not say why, and it fails all at once when anything upstream changes. Bounds,
rounding, ordering and every refusal path are tested directly, where a failure names the
thing that broke.
