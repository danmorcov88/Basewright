# ADR-0008: Python decides, Ansible acts

**Status:** Accepted · 2026-09-03

## Context

Two different kinds of work happen in this tool, and they have almost nothing in common.

One is deciding. Normalising messy host facts into a usable model, evaluating gate rules
against thresholds, computing `work_mem` as a quarter of memory divided across twice the
connection limit, clamping it to a minimum, rounding it to something a config file will
accept, and recording which rule produced it. This is arithmetic and branching over data,
run entirely on the control node, with no host involved.

The other is acting. Adding a repository, installing packages, creating accounts and
directories with the right modes, writing config files, setting sysctl values, enabling a
service. This is remote, stateful, needs to be idempotent, needs to handle several OS
families, and is exactly what a configuration management tool is for.

Ansible can express both, and that is the problem. Sizing arithmetic written in Jinja is
technically possible and practically unreviewable: a nested chain of `| int`, `| min`,
default filters and inline conditionals, spread across `vars/`, `defaults/` and group_vars,
with precedence rules that decide which one wins. It cannot be unit-tested without running a
playbook, so it is tested by running it against a host and seeing whether the number looks
right — which is not a test, and does not scale to a table of fixture machines with 2 GiB,
512 GiB, rotational disks and a full backup mount.

Writing the acting half in Python has the mirror problem: reimplementing idempotent package
and file management, badly, for two OS families.

## Decision

The two halves are separated, and the plan is the boundary between them.

**Python decides.** Everything under `basewright/`: fact normalisation, gate evaluation,
severity resolution, sizing arithmetic, bounds and rounding, layout resolution, plan
assembly, and rendering. It is a library with a thin CLI, it touches no host, and it is
tested with pytest over fixture data.

**Ansible acts.** Everything under `ansible/`: repositories, packages, accounts,
directories, templates, sysctl, services, and the verification reads. Roles are idempotent
and thin. They consume `plan.json` and execute it.

**Ansible decides nothing.** No sizing arithmetic in a template, no gate logic in a `when:`,
no threshold in `defaults/main.yml`. A role that computes a value is a defect, not a
shortcut. Where a role needs a value, the plan carries it; if the plan does not, the plan is
incomplete and the planner is what changes
([ADR-0001](0001-plan-before-apply.md)).

Templates render values that were already decided. `postgresql.conf.j2` substitutes; it does
not calculate. A `when:` may branch on OS family for *how* to install something — that is
mechanism, not decision — but never on a threshold or a computed size.

Action plugins under `ansible/plugins/` bridge the two, calling into the Python package so
there is one implementation of every decision rather than one per side.

## Consequences

The interesting logic is testable in milliseconds without a host. The table-driven tests the
brief calls for — a machine with 2 GiB, one with 512 GiB, one with rotational disks, one
with a full backup mount — are ordinary unit tests, and golden plan fixtures make a change
to a sizing rule visible as a readable diff in the pull request. Neither is achievable if the
arithmetic lives in Jinja.

The roles get simpler, which makes them genuinely reviewable. A role that installs a package
and writes a template with values it was handed can be read in a minute and molecule-tested
in a container.

The split also makes [ADR-0002](0002-engines-are-data.md) enforceable. Because the deciding
half is one Python package, "no engine name in the core" is a check that can be run over a
directory. If decisions were spread across roles and vars files, there would be no core to
check.

The costs: two languages and two toolchains in one repository, a serialisation boundary that
has to stay in step with a schema, and a rule that will feel obstructive at least once a
month. Somebody will want a small default in `defaults/main.yml` because it is three lines
there and a schema change plus a planner change plus a test here. That is exactly the change
this decision exists to refuse — the three-line version is how the reasoning got invisible in
the first place.

There is also a real constraint on what the roles can do: a role cannot adapt to something it
discovers mid-run. If a host turns out to differ from the facts the plan was built on, the
role's move is to refuse and ask for a fresh plan, not to improvise
([ADR-0010](0010-idempotency-match-or-refuse.md)).

## Rejected alternatives

**Everything in Ansible, with sizing in Jinja and custom filter plugins.** One language, one
toolchain, no boundary to keep in sync — and filter plugins are Python, so some testing is
possible. Rejected because the composition still happens in templates and variable
precedence, which is the untestable part. The tests would cover the filters and miss how they
are combined, which is where the mistakes are.

**Everything in Python, driving hosts over SSH directly.** No second toolchain, complete
control, and the decisions and actions in one language. Rejected because it means writing
idempotent package, file, service and sysctl management for multiple OS families — a large,
dull, bug-prone body of work that Ansible has already done well, and that the team already
knows.

**Ansible calling a Python planner, but roles free to compute where convenient.** The
pragmatic middle: use the planner for the hard sizing, let roles handle small derivations.
Rejected because "where convenient" has no stable boundary. Once a role may compute
anything, the question of where a value came from stops having a mechanical answer, and the
plan is no longer a complete description of what will happen.

## Related

- [ADR-0001](0001-plan-before-apply.md) — the plan is the boundary, and apply reads nothing
  else.
- [ADR-0002](0002-engines-are-data.md) — the other axis of the same separation.
- [ADR-0009](0009-sizing-rules-explain-themselves.md) — what the deciding half evaluates.
- [ADR-0010](0010-idempotency-match-or-refuse.md) — why a role refuses instead of adapting.
