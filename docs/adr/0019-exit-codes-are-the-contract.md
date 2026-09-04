# ADR-0019: Exit codes are the contract with Semaphore

**Status:** Accepted · 2026-09-04

## Context

Semaphore is the interface (ADR-0005), and Semaphore's view of a run is one bit: the task
is green or the task is red, decided by the process exit code. Everything else Basewright
produces — the refusal report, the plan, the rendering with every value and its rule — sits
inside the task log, where somebody reads it after the colour has already told them to look.

Four codes are already returned, and until now nothing said what they meant. `0`, `2`, `64`
and `69` were four constants near the top of `cli.py` with a comment each, no test held them
as a set, and no document a template author could read named any of them. That is the shape
a contract has just before it drifts: a fifth code gets added for a case that felt different
on the day, someone's template starts branching on the number, and the meaning of `2` is
whatever the last person to touch it thought.

The pressure to add codes is real, because the outcomes genuinely differ. A gate that
blocked a host, a facts document that fails its contract, a plan that has been edited by
hand since it was produced, and — when it arrives — a verify run that found the instance no
longer matches its plan: four different things happened. The question is whether they are
four different things *to the person reading a red task*.

There is a second pressure in the other direction. `69` names a verb that exists and is not
built. It is the only code with an expiry date on it: when `verify` lands, nothing returns
it any more. A contract with a member that is scheduled to disappear needs to say so before
it disappears, or its removal reads as a break.

## Decision

**There are four exit codes, they are a closed set, and each one answers a single question:
what does the person reading this task do next?**

| Code | What happened | What to do |
| ---- | ------------- | ---------- |
| `0`  | The tool ran, and the answer is yes | Go on to the next step |
| `2`  | The tool ran, and the answer is no | Read the report |
| `64` | The request itself is malformed | Fix the command |
| `69` | The verb exists and is not built yet | Nothing yet |

**The line between `2` and `64` is where a document stopped being readable.** A file that
could not be read at all is `64`; a file that was read and is not acceptable is `2`. A
missing facts document is a mistyped path, so it is `64`. A facts document that fails its
contract is a real answer about a real file, so it is `2`, and there is a refusal report
naming every field that was wrong. A plan whose id no longer matches its own content is `2`
for the same reason: it is a plan, it is simply not the plan it claims to be, and saying so
is an answer rather than an error.

**A blocked gate, an unacceptable document and a verify mismatch are all `2`.** They differ
in what happened and not in what to do about it. Each one means Basewright ran, reached a
conclusion, and wrote a report explaining it, and in each case the next action is to read
that report. The report is where the difference between them lives, in full and in prose,
which is a better place for it than a number.

**`69` is temporary, and its removal narrows the set rather than changing it.** It leaves
when the last unbuilt verb is built. Anything that treats non-zero as red — which is
Semaphore, and every reasonable script — is unaffected by a code it stops seeing.

**The set lives in code, as `EXIT_CODES` in `basewright/cli.py`.** The README table and the
diagram in `docs/assets/` are rendered from it, and `test/unit/test_cli.py` holds it in both
directions: every code in the set is reachable from a real invocation, and the CLI returns
no code that is not in the set.

## Consequences

A Semaphore template author has one page to read, and it tells them the only thing a
template needs: red means read the log, and the log always contains the reason.

Adding a fifth code becomes a decision with a document attached rather than a line in a
diff. The bar it has to clear is stated: a new code must mean a genuinely different *next
action*, not a genuinely different cause. Almost nothing clears that bar, which is the
point.

`2` is doing a lot of work, and that is a real cost. A script that wants to tell a blocked
gate from a tampered plan cannot do it from the exit code and has to read the JSON artifact.
That is the correct place for it — the artifacts are machine-readable precisely so that
machines read them instead of inferring from a number — but it does mean the exit code is
not a sufficient interface for automation more ambitious than Semaphore's.

Holding the set in a test means a new code cannot be added quietly. It also means the test
has to be updated when `69` goes, which is the reminder that its removal is a contract
change rather than a cleanup.

Codes `64` and `69` follow `sysexits.h`, so they read correctly to anyone who has met that
convention and are meaningless-but-harmless to anyone who has not. `2` is not from that
list; it is the conventional "the tool worked and disagreed with you" code that `grep` and
`diff` use, which is exactly what it means here.

## Rejected alternatives

**A distinct code per outcome — say `3` for a tampered artifact and `4` for a verify
mismatch.** More information at the process boundary, at no cost in complexity. Rejected
because none of them changes what the operator does, and a number that does not change the
next action is a number nobody learns. The predictable end state is a template that branches
on `3` in a way that silently stops matching when a fifth code arrives.

**One non-zero code for everything.** Simpler still, and honest about Semaphore only having
two colours. Rejected because it loses the one distinction that does change behaviour: `64`
means nothing was decided and there is no report to read, so a person staring at the log
looking for the reason is wasting their time. Telling "we disagreed with you" apart from
"we did not understand you" is worth one number.

**Reserve a code for a run that blocked, so that Semaphore's Apply template can refuse to
start.** Tempting, and it is why this was considered at all. Rejected because it puts a gate
decision in a number, and a number is the kind of thing a run-time flag can be written
against. ADR-0004 says a block is never overridable at run time; the way to keep that true
is for the refusal to live in the artifact apply reads, not in a signal a wrapper can catch.

**Leave the codes undocumented until Phase B, when the Semaphore templates are actually
written.** The templates are the consumer, so waiting for them is defensible. Rejected
because the codes exist and are already being returned; the cost of writing them down now is
one document, and the cost of writing them down later is whatever was built against a
meaning nobody had agreed on.

## Related

- [ADR-0005](0005-semaphore-is-the-interface.md) — who reads these codes, and why there is
  no second interface that could read something richer.
- [ADR-0004](0004-two-severities-no-override.md) — why a block must not be catchable as a
  signal.
- [ADR-0001](0001-plan-before-apply.md) — the artifact a `2` always points at.
- [ADR-0017](0017-a-plan-is-named-by-its-content.md) — the check that produces a `2` for a
  plan that has been edited.
