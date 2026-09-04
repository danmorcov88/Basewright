# ADR-0016: A plan carries canonical values, not rendered ones

**Status:** Accepted · 2026-09-04

## Context

A sizing rule works out that a cache should be eight gibibytes. Three separate readers need
that answer, and they do not want it in the same form.

The **configuration file** wants it spelled the way the engine parses it. One engine reads
`8GB`. Another reads `8G`. A third wants an integer count of megabytes and will refuse a
suffix. A fourth counts in eight-kilobyte blocks and would read `1048576`.

The **person reviewing the plan** wants `8.0 GiB`, because `8589934592` is a number nobody
checks and a diff of two such numbers tells a reviewer nothing about what changed.

**Verify** wants to compare. It asks the running instance what the parameter is, gets back
whatever that server chose to print, and has to decide whether the promise in the plan was
kept. That is the reader that settles it: comparing rendered text against a server's own
formatting is not a comparison. It is a string equality test that fails when a server prints
`8192MB` for a value that is exactly right, and passes when it prints `8GB` for a parameter
that silently got clamped somewhere else.

The first draft of the contract had one field, `value`, described as *rendered as the
engine's configuration file expects to read it*. Which cannot be right, because the core
that produces the plan does not know the engine — it cannot know that this one writes `8GB`
and that one writes `1048576`, and finding out would mean the planner branching on an engine
name, which is the one thing it may never do.

## Decision

**A parameter carries three fields where it used to carry one.**

- `value` is **canonical**: a count of bytes, a number of seconds or milliseconds, a plain
  number, a ratio, or the word itself. It is what a comparison is made on.
- `unit` says what it is measured in, so that a reader and a comparison mean the same thing
  by the number.
- `display` is the value as a person reads it — `8.0 GiB` — and exists for one reason: the
  diff of two golden plans is the review mechanism for a tuning decision, and a diff of raw
  byte counts is not reviewable.

**Rendering into the engine's own syntax happens in the engine's own template.** That is
where the syntax of one engine belongs, next to everything else about that engine, in the
profile.

**Verify compares `value`.** It normalises what the server reported into the same canonical
unit and compares numbers. A parameter that reads back as the same quantity spelled
differently is a match, because it is one.

## Consequences

The plan gets larger and slightly more redundant: three fields where a reader might expect
one, two of which are derived from the third. That is the price of one document serving a
machine and a person, and it is paid once per parameter.

Verify becomes possible to write honestly. Without this it would either compare strings —
and be wrong in both directions — or re-derive the canonical value from the rendered one,
which means the core parsing the engine's configuration syntax, which is the same
prohibited knowledge arriving by another door.

The golden plans stay readable. A change to a sizing rule shows up in a pull request as
`"display": "8.0 GiB"` becoming `"display": "16.0 GiB"`, which a reviewer can judge without
converting anything.

`display` is rendered by the core, in binary units, one decimal place. It is not the
engine's spelling and it is not trying to be; it is the plan's own way of writing a
quantity, and it is the same for every engine so that two plans can be read side by side.

The unit list is closed: bytes, milliseconds, seconds, count, ratio, text. An engine whose
parameter is measured in something else needs the schema extended, which is a version of
the contract and a conversation. That is deliberate — an open unit field would be a place
for an engine to smuggle in a rendering the core does not understand.

## Rejected alternatives

**Keep one rendered `value`.** The smallest contract, and the plan reads exactly like a
configuration file. Rejected because producing it requires the core to know the engine's
syntax, and because verify cannot then do its job. Every way of rescuing it — a lookup
table of syntaxes, a rendering hint per engine, parsing the value back — ends with engine
knowledge in the core or with the canonical number reintroduced under another name.

**Let the profile declare a rendering, from a closed set the core implements.** A `render`
field on a sizing rule choosing between a binary suffix, a decimal suffix, whole mebibytes,
or a plain number. The profile chooses, the core renders, no engine name in the core. This
was the closest call. Rejected because it solves the wrong half: it makes `value` correct
for the configuration file and leaves verify having to invert the rendering to compare, and
because the set would have to grow for every engine with an unusual spelling — which is a
closed set with an open-ended queue behind it. Rendering already has a natural home in the
template, which is data the profile owns and which no schema has to enumerate.

**Carry the canonical value only, and let the report derive the display.** One less field.
Rejected because the golden plan is the artifact under review, not the report, and a
reviewer reading a diff of the plan should not have to run anything to know what changed.

**Two documents: a machine plan and a human plan.** Clean separation, each perfect for its
reader. Rejected because two documents drift, and because the plan's whole claim is that
the thing apply executes is the thing somebody approved.

## Related

- [ADR-0001](0001-plan-before-apply.md) — the plan as a reviewable artifact.
- [ADR-0002](0002-engines-are-data.md) — why the core cannot know the engine's syntax.
- [ADR-0009](0009-sizing-rules-explain-themselves.md) — why a value travels with its reason.
- [ADR-0017](0017-a-plan-is-named-by-its-content.md) — what the fields above are digested
  into.
