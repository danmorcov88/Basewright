# ADR-0002: Engines are data, not code

**Status:** Accepted · 2026-09-03

## Context

A tool that provisions more than one database engine has to put the differences between
those engines somewhere. There are only two places available: in the logic, as branches on
which engine is being installed, or in data the logic reads.

The first is what happens by default, because it is what each individual change makes
easiest. The first engine needs no abstraction at all. The second engine adds a handful of
conditionals, each of them locally reasonable. By the third, the planner contains a
decision tree that only its author can read, every engine's behaviour is smeared across
files that are nominally shared, and adding a fourth engine means understanding the other
three well enough not to break them.

This project expects that pressure. The roadmap has PostgreSQL first, then MySQL/MariaDB,
then SQL Server, and the whole premise is that a fourth engine is a contribution somebody
else can make. That is only true if adding one does not require reading the core.

There is also a review argument. The interesting content of an engine profile — which OS
versions are supported, what the minimum memory is, why `shared_buffers` is a quarter of
RAM — is exactly the content a DBA is qualified to review and a programmer is not. Buried
in Python, it is invisible to the person best placed to judge it.

## Decision

**No module under `basewright/` may branch on, or refer to, the name of a database engine.**

Everything engine-specific lives in `profiles/<engine>/`: a directory of declarative YAML
plus one thin Ansible role that applies what the plan decided. The core reads profiles
through a JSON Schema and treats them as opaque data.

When the core appears to need the engine name to behave correctly, that is a signal the
profile schema is missing a field. The schema is extended so a profile can supply the
information, and the core stays generic. Adding a conditional is not an available option,
even as a temporary one.

The rule is enforced rather than trusted:

- `test/unit/test_engine_names_absent_from_core.py` scans every source line under
  `basewright/` — comments and docstrings included, because an example in a docstring is how
  the first engine name usually gets in — and fails on a match. It runs as its own CI job so
  the failure is unmistakable in the checks list. Its exemption list is empty.
- Profiles are validated with `additionalProperties: false` throughout, so a profile cannot
  introduce a key the core does not already understand, which is the other direction the
  abstraction can leak.
- A second engine ships in Phase C specifically to test the claim, and it ships without
  modifying anything under `basewright/`. If the core has to change, that is the finding,
  and it is answered with a schema extension.

## Consequences

Adding an engine is a change to `profiles/`, reviewable by a DBA. That is the contribution
surface the project wants, and it is available to people who would never send a pull request
against a planner.

The core stays small and its tests stay meaningful. A gate is tested against fixture facts
and fixture thresholds, not against "what PostgreSQL does", so the tests describe behaviour
rather than restating an engine's manual.

The cost is real and is paid up front. Every engine-specific capability has to be expressed
generically before it can be used at all, and the first expression is usually wrong. A
parameter that is trivially `if engine == ... then ...` in an afternoon becomes a schema
change, a validation update, a profile field and a test. Some of those generalisations will
be built on a single example and will need widening when the second engine arrives.

There is also a discipline cost in reviews. The pressure to add "just one" conditional is
strongest when a release is close, which is precisely when the enforcement is worth having,
and precisely when it will be resented.

One engine proves nothing about any of this. Until Phase C lands, the claim that the
abstraction holds is a hypothesis, and the status page says so.

## Rejected alternatives

**A plugin base class with per-engine subclasses.** The object-oriented version: an
`Engine` interface, one subclass each. Rejected because it moves the branch rather than
removing it. Behaviour still lives in Python, so a contribution is still a code change,
still needs a programmer, and still needs the core's tests to be understood. It also invites
subclasses to reach for state they were not given, which is the failure the schema's closed
key set prevents.

**Conditionals now, abstraction when a third engine arrives.** The pragmatic position, and
often the right one. Rejected here because the refactor never happens on a schedule that
helps: by the time the third engine makes the cost obvious, the conditionals are load-bearing
and untangling them is a project of its own. The cost of generalising early is bounded and
visible; the cost of generalising late is neither.

**A small expression language for engine-specific escapes.** Let a profile carry a snippet
the core evaluates when the declarative fields do not stretch far enough. Rejected because
it is a conditional with extra steps and worse tooling. It would let a profile smuggle in
behaviour, which is the exact thing `additionalProperties: false` exists to stop, and it
would be untestable in the way the sizing rules are testable.

## Related

- [ADR-0008](0008-python-decides-ansible-acts.md) — the other axis of the same separation.
- [ADR-0009](0009-sizing-rules-explain-themselves.md) — what a declarative rule looks like
  in practice.
- [ADR-0003](0003-humans-choose-the-version.md) — the support matrix is profile data for the
  same reason.
