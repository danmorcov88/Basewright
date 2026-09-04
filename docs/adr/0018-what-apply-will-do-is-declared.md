# ADR-0018: What apply will do is declared, not inferred

**Status:** Accepted · 2026-09-04

## Context

The plan promises a list of everything apply would do. The sample in the brief reads:

```
+ add apt repository
+ install the packages
+ create the service account
+ create 4 directories
+ write the server configuration (23 parameters), and the access rules (3 rules)
~ set vm.swappiness 60 -> 10
+ enable and start the service unit
```

Most of that is already declared somewhere. The repository, the package names and the
service unit are in `packages.yml`. The account and the directories are in `layout.yml`.

Three of them are not declared anywhere, and they are not small.

**Which configuration files get written, and where.** A profile has a `templates/`
directory and nothing that says what any template renders into, with what mode, or which of
them carries the sized parameters. Without that the plan can promise values and cannot say
what file they end up in — and apply, which consumes the plan and nothing else, has nowhere
to write them.

**Which host settings get changed.** `requirements.yml` declares a `preferences` block that
a warning rule reads: *this engine prefers swappiness at or below ten*. That is a threshold
for judging a host, not an instruction for changing one. Reading a target value out of a
preference would mean inferring an action from a judgement, and the two are different
sentences: a host at swappiness 8 satisfies the preference and would be moved to 10 by the
inference.

**Which secrets the instance needs, and where they are kept.** Nothing declares them at all.

The pressure to infer is real, because inference is less work and looks tidier. Every form
of it ends the same way: the core deciding that a file called `*.conf.j2` probably goes in
`/etc/<engine>/`, or that a preference is also a target, or that every engine has exactly
one administrative password. All of those are engine knowledge, arrived at by guessing.

## Decision

**A profile gains an eighth file, `apply.yml`, and its own closed schema.** It answers the
one question none of the other seven answers: what apply will do to the machine.

```yaml
configuration:                 # what gets written, where, with what mode and owner
  - id: ...
    template: server.conf.j2
    destination: /etc/basewright/{{ engine }}/{{ instance }}/server.conf
    mode: "0640"
    carries_parameters: true
tunables:                      # host settings, what they become, and what they are now
  - name: vm.swappiness
    value: 10
    observed: host.kernel.swappiness
    why: ...
secrets:                       # a name and a place. There is no third field.
  - name: administrative account password
    location: basewright/{{ host }}/{{ engine }}/{{ instance }}/admin
```

Three choices inside it are the ones worth defending.

**`carries_parameters` is a boolean, not a description of contents.** The only thing the
core has any business knowing about the inside of a configuration file is which one the
sized parameters go into, so that the plan can say *write this file, with six parameters in
it*. Anything richer would be the core learning what a configuration file contains.

**`observed` is an expression, not a setting name the core maps.** It reads
`host.kernel.swappiness` through the same interpreter every gate rule uses. The alternative
is a table inside the core translating `vm.swappiness` into a fact — a table that has to
grow every time a profile wants a setting nobody anticipated, and which is a list of
operating-system knowledge sitting in the part of the tool that is supposed to have none.

**`apply.yml` is required.** Every engine writes a configuration file; a profile without
this section produces a plan that is quietly incomplete, and quiet incompleteness is the
thing this project exists to replace. `tunables` and `secrets` may be absent, and absent
means the engine asks nothing of the host and needs no secret — which is a statement rather
than a silence.

**The plan carries all three as structured sections, and the narrative separately.** The
`changes` list is prose for the person who signs it. `packages`, `configuration` and
`tunables` are what apply executes. They are not the same list: one is written for somebody
to read and one for a machine to follow, and collapsing them means one of the two is wrong.

## Consequences

`plan.json` grows three sections and becomes genuinely sufficient for apply. That was the
rule all along — *apply consumes the plan and nothing else* — and until now the plan could
not have honoured it.

A profile author has one more file to write, and it is the file where the reviewable
decisions live: where configuration lands, what the instance is allowed to change about the
host, and what secrets exist. That is a good place for a reviewer to be looking.

The loader gains two checks that could not exist before: at most one configuration file may
claim the parameters, and every template named has to be present in the profile. A plan
promising a file the profile cannot render would otherwise fail halfway through apply, on
somebody else's machine, with the packages already installed.

The count in the documentation moves from seven files to eight, in the anatomy diagram, in
`writing-a-profile.md`, and in the loader's own refusal message. The diagram is generated
and a test holds it against the loader's list, so the picture cannot fall behind.

A host that does not report a setting still gets the change: the plan lists it without a
`from` rather than with a guess.

## Rejected alternatives

**Spread the three sections through the existing files.** Configuration into `layout.yml`,
because destinations are paths; tunables into `requirements.yml` next to `preferences`;
secrets into `profile.yml`. No new file, no new schema. Rejected because each of the seven
files answers exactly one question, and this would give `layout.yml` two of them and make
`requirements.yml` mix *what refuses a host* with *what gets changed on it* — which is the
distinction the whole preflight-then-apply split rests on.

**Build `changes` from what can already be inferred, and defer the rest.** The smallest
change, and it produces a plausible-looking plan today. Rejected because the contract
freezes with this release: a `changes` list that can never mention a configuration file or
a host setting without a version bump is worse than the version bump.

**Let `preferences` double as the target for a tunable.** No new section: the profile
already says it prefers swappiness at or below ten, so set it to ten. Rejected because a
threshold and a target are different statements. A host at 8 already satisfies the
preference and would be *raised* to 10 by the inference, which is an instance of a tool
changing a machine for a reason nobody wrote down.

**Declare the whole change list in the profile, as data.** Fully general: the profile writes
every line of `changes` and the core substitutes into them. Rejected because it duplicates
what `packages.yml` and `layout.yml` already say, and duplication in a profile is how the
narrative and the actions drift apart — the plan would then be able to promise something
apply does not do.

**An `initialization` section, for the step that creates the instance itself.** Every engine
has one. Rejected for now as out of scope rather than wrong: apply does not exist yet, so
the section would carry a description nobody can act on, and its shape is a question the
Phase A role is the right place to answer. It is a schema addition when there is something
to consume it, and the contract's version rules say what that costs.

## Related

- [ADR-0002](0002-engines-are-data.md) — the rule this file exists to obey rather than
  work around.
- [ADR-0001](0001-plan-before-apply.md) — why apply reads the plan and nothing else.
- [ADR-0007](0007-secrets-never-in-artifacts.md) — why a secret entry has two fields.
- [ADR-0014](0014-rules-are-expressions-not-code.md) — the interpreter `observed` is read by.
