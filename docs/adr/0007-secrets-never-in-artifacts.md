# ADR-0007: Secrets never appear in inventory, plans, facts or logs

**Status:** Accepted · 2026-09-03

## Context

Provisioning a database instance involves credentials at several points. The technical
account needs a key to reach the host. The engine needs an administrative password, usually
generated. A replication or monitoring role may need one too. Some of those values are
consumed once and never again; all of them are worth stealing.

Meanwhile this project deliberately produces artifacts and expects them to travel. The plan
is meant to be attached to a change request, committed to Git, and read by a second person.
Facts are collected and kept for the planner to consume. Task logs are retained in Semaphore
so a run can be reconstructed months later. Every one of those is a place a secret can come
to rest, and each has a different, usually longer, retention than anybody intends.

Secrets leak into artifacts in a small number of well-known ways, and none of them look
careless at the time:

- A password passed on a command line. Visible to every process on the host through `ps`,
  and written to shell history.
- A generated password echoed by the task that created it, so the operator can see it
  worked, and thereby written to the task log forever.
- A credential in the inventory, because the inventory is the natural place to put things a
  playbook needs, and the inventory is in Git.
- A value included in the plan so `apply` can consume it, because `apply` reads only the
  plan ([ADR-0001](0001-plan-before-apply.md)) and that rule is otherwise absolute.
- A password captured as a fact, because the fact gatherer read a config file.

The last of these is the sharpest conflict in the design: the plan is the sole input to
apply, and the plan must be safe to share.

## Decision

No secret is written to an inventory, a plan, a fact document, a report, or a log. This is
absolute and has no per-environment exception.

Concretely:

- **Credentials are injected at run time** from Semaphore's secret store or from
  `ansible-vault`. They are not committed, and they are not in the inventory.
- **No password is accepted on a command line.** Environment variable or standard input.
  There is no `--password` flag and there will not be one.
- **Generated passwords are written once, to the secret store, and never read back into an
  artifact.** The plan records the *location* — `password: <generated, stored as
  basewright/db-prod-07/gitrez/admin>` — not the value. `apply` fetches from that location,
  which resolves the conflict with "apply reads only the plan": the plan carries the
  reference, and the reference is not a secret.
- **The task log shows that a password was set, never what it was.** Ansible tasks handling
  credentials are marked `no_log`, and the fact that a task is `no_log` is itself part of
  what gets reviewed.
- **Fact gathering does not collect credential material.** A config file is read for the
  settings that matter; anything that looks like a credential is not carried into the fact
  model, so it cannot reach a plan by accident.

**The plan is safe to share by design.** That is a requirement to test against, not a
property to hope for.

## Consequences

The artifact the whole project is built around can be handed to anybody — a reviewer, a
change board, a ticket, a public repository — without a redaction step. Redaction steps are
the thing that eventually gets skipped.

The blast radius of an artifact leak is bounded. A stolen plan describes an intended
configuration, which is not nothing, but it does not authenticate anybody to anything.

Costs, honestly stated. Debugging is harder: when authentication fails, the log says a
credential was used and not which one, so diagnosis leans on the secret store's own audit
rather than on the task output. Recovering a generated password means going to the secret
store, and if the write to the store failed while the engine-side change succeeded, the
credential is lost and has to be reset — so that write is not fire-and-forget.

The secret store becomes a hard dependency of `apply`. That is deliberate: the alternative
is a fallback path, and a fallback path for secrets is where secrets end up.

There is also a permanent review obligation. Every new task that touches a credential is a
chance to reintroduce this, and `no_log` is easy to forget. Its absence has to be something
a reviewer looks for.

## Rejected alternatives

**Passwords in an `ansible-vault`-encrypted inventory, committed to Git.** Standard
practice, and better than plaintext. Rejected as the primary mechanism because an encrypted
secret in Git is still a secret in Git: it is subject to the vault password's own
distribution problem, it cannot be rotated without a commit, and it survives in history
after rotation. Vault remains supported for environments without a secret store; it is not
the default.

**Putting the generated password in the plan so apply is genuinely self-contained.**
Architecturally cleaner, and it would preserve "apply reads only the plan" without an
exception. Rejected because it destroys the property that makes the plan useful. A plan that
cannot be attached to a ticket is a plan nobody reviews, and a reviewed plan is worth more
than a self-contained one. Carrying a reference rather than a value keeps both.

**Printing the generated password once, at the end of the run.** Operationally convenient —
the operator can copy it immediately. Rejected because "printed once" is not true when the
run is a Semaphore task: the output is a retained log, readable by everyone with access to
that project's history, indefinitely.

**Redacting secrets from logs with output filtering.** A safety net that catches what
`no_log` misses. Rejected as a primary control because it is pattern matching against
arbitrary output, and it fails open — an unmatched format is silently logged in full. It
would also encourage treating secrets in output as a formatting problem rather than a design
error. Not collecting the value is the control; there is nothing to filter.

## Related

- [ADR-0001](0001-plan-before-apply.md) — the plan is the only input to apply, and why the
  reference rather than the value is what it carries.
- [ADR-0006](0006-dedicated-technical-account.md) — the credential that reaches the host.
- [ADR-0005](0005-semaphore-is-the-interface.md) — where secrets are stored and injected
  from.
