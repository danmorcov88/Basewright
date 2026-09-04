# ADR-0014: A rule a profile writes is an expression, read by an interpreter that cannot run anything

**Status:** Accepted · 2026-09-04

## Context

A profile contributes gate rules and sizing rules, and both carry a condition as a string:

```yaml
expr: host.memory.total_bytes >= 2 * GiB
expr: (0.25 * host.memory.total_bytes) / (max_connections * 2)
expr: 1.1 if not path.data.rotational else 4.0
```

Something has to turn those strings into answers. The choice is constrained from three
directions at once.

It has to be **safe**. A profile is a file the tool reads at run time, on a control node
that holds credentials for every host in the estate. Whatever reads these strings is a
place where text becomes behaviour, and the only defensible position is that the text
cannot express behaviour at all — not that it is unlikely to, or that the profiles in this
repository happen not to.

It has to be **readable by the person reviewing the profile**, who knows the engine and may
not write Python. A pull request that changes a threshold has to be a diff somebody can
form an opinion about without a debugger.

And it has to be **the same machinery for gates and for sizing**. Two dialects that are
almost the same is the worst outcome available: an author would write a working expression
in one file, copy it into the other, and find out at run time that one of them supports
`if`/`else` and the other does not.

Two obvious answers were ruled out before the question was really open.
[ADR-0008](0008-python-decides-ansible-acts.md) puts deciding in Python, so a template
language is not a candidate: Jinja would move the arithmetic back into templates, which is
the thing that decision exists to prevent. And `eval` is not a candidate under any framing.
It runs whatever it is handed, `__import__` included, and the mitigations people reach for
— stripping `__builtins__`, blocking a list of names — are known to be escapable through
attribute traversal from any object the expression can reach.

## Decision

The expressions are a small language of their own, and
[`basewright/expressions.py`](../../basewright/expressions.py) is the only thing that
reads them. Both the gate engine and, from the next slice, the sizing evaluator use it.

**The syntax is Python's, and is parsed by `ast.parse(mode="eval")`.** That is a borrowing
of the tokenizer, the precedence table and the column numbers in error messages — three
things that are tedious to write and worse to get subtly wrong. Nothing is compiled and
`eval` is never reached.

**The meaning is supplied by a walk over an allowlist of node types.** Constants, names,
attributes, arithmetic, comparison, `and`/`or`/`not`, a conditional expression, and tuple
literals for membership tests. Everything else is refused when the expression is *read*,
before any host is involved, with the construct named and the column it appears at:

```
requirements.yml:rules[2].expr: column 14: a function call is not part of this
  language. Expressions read facts and compare them; they do not call, index or
  build anything.
```

Calls, subscripts, lambdas, comprehensions, formatted strings, dict and set literals,
unpacking, assignment expressions and `await` are all rejected there. So is any name or
attribute beginning with an underscore.

**Names resolve through nested mappings of plain values, never through `getattr`.** The
scope an expression is evaluated against is built in
[`basewright/preflight/scope.py`](../../basewright/preflight/scope.py) out of strings,
numbers, booleans and tuples. No object of ours ever enters an expression, so the standard
walk from an attribute to a type to the interpreter has nothing to start from. This is what
makes the safety structural rather than a matter of maintaining a blocklist.

**Exponentiation is absent.** It is the one operator whose cost is unbounded by the length
of the expression, and no sizing rule has ever needed it.

**Everything is strict about types.** Only a genuine boolean is a yes or a no: a rule that
leans on an empty string being false is a rule whose reader has to know Python's truthiness
table, and the point of the language is that they do not. Arithmetic is on numbers only.
Ordering comparisons refuse to compare a size against a name.

**Two failures are deliberately different.** An expression that reads a fact the vocabulary
defines but the host did not report raises `Unreported`, and the rule that contains it
reports `skip` — a reportable outcome, not a guess. An expression that mentions something
the vocabulary does not define at all raises, and refuses the run: a misspelled fact is a
defect in the profile, and a silent skip would be a gate that has quietly stopped guarding.

## Consequences

The safety argument fits in a paragraph and can be checked by reading one file. There is no
sandbox to keep patched, no list of forbidden names to keep current, and no dependency
whose threat model has to be trusted.

A profile author gets errors that point at a column, which is the difference between fixing
an expression in one edit and fixing it in four. They also get the syntax they already
expect from every configuration language they have used, without having to learn which
subset of it is real — because the subset is enumerated in the refusal when they leave it.

Sizing inherits all of this for free in the next slice. The unit constants (`2 * GiB`) are
already there, and the bounds and rounding a sizing rule needs sit outside the expression
rather than inside it, which keeps the language small.

The costs are real. The language is not extensible by a profile: an engine that genuinely
needs a function will need the function added to the core, reviewed, and made available to
every profile — which is friction, and is meant to be, since the alternative is each
profile inventing its own vocabulary. Borrowing Python's grammar also means an author can
write something syntactically valid that this refuses, and the refusal has to be good
enough to explain why; that is a documentation burden that does not go away.

And there is a genuine limit, which [ADR-0015](0015-shared-gates-are-code.md) is about: an
expression returns a yes or a no, so a rule written as one cannot report the value it
observed against the value it required. That is fine for a rule an engine adds about
itself, and not fine for the twenty rules that refuse hosts for everyone.

## Rejected alternatives

**`eval`, with `__builtins__` stripped and a blocklist of names.** Three lines, supports
the whole language, and every author already knows it. Rejected because it is not a
security boundary. Given any object, attribute traversal reaches its type, its base
classes, its subclasses and from there the import machinery; the published escapes are
short enough to fit in a tweet. A profile is data the tool reads at run time on a machine
holding estate-wide credentials, and "no untrusted profile is expected here" is a property
of today's repository rather than of the design.

**A hand-written tokenizer and precedence-climbing parser.** Complete control of the
grammar, no implied Python semantics, and a language that could be documented without
reference to another one. Rejected on cost against benefit: roughly three hundred lines
before the first rule evaluates, and precedence, associativity and unary minus are exactly
the things that are quietly wrong for a year. The allowlist walk over `ast` is a fifth of
the size and the parsing half of it is already tested by CPython.

**`simpleeval` or `asteval`.** Existing libraries for this exact problem, with more
features than this needs. Rejected because both hand the expression real Python objects to
traverse, so the attribute surface has to be closed here anyway; because their threat model
is theirs and changes on their schedule; and because their error messages are theirs, which
would make expression failures the one kind of refusal in this tool that does not read like
the others.

**Jinja, since Ansible is already a dependency.** One templating language across the whole
repository. Rejected by [ADR-0008](0008-python-decides-ansible-acts.md): sizing arithmetic
in Jinja is unreviewable and untestable without running a playbook, and this is the
mechanism by which it would arrive.

**Structured conditions instead of strings** — `{fact: host.cpu.cores, op: gte, value: 2}`.
No parser at all, and trivially safe. Rejected because it is a worse language, not the
absence of one: `(0.25 * memory) / (max_connections * 2)` becomes a nested tree of
operation objects that nobody can read in a diff, and the review of a tuning change is the
thing that matters most about sizing rules
([ADR-0009](0009-sizing-rules-explain-themselves.md)).

## Related

- [ADR-0008](0008-python-decides-ansible-acts.md) — why the deciding is Python, and why a
  template language was never a candidate.
- [ADR-0009](0009-sizing-rules-explain-themselves.md) — the other consumer of this
  machinery, and why a rule has to be readable in a diff.
- [ADR-0015](0015-shared-gates-are-code.md) — where an expression is not enough, and why.
- [ADR-0002](0002-engines-are-data.md) — the language is how an engine states a rule
  without the core learning anything about it.
