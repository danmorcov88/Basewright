# ADR-0006: A dedicated technical account reaches targets, never personal keys

**Status:** Accepted · 2026-09-03

## Context

Basewright connects to hosts and performs privileged operations on them: installing
packages, creating system accounts, writing into `/etc`, setting sysctl values, enabling
services. Something has to authenticate for that, and the choice determines what the audit
trail is worth.

The path of least resistance is whoever is running the job. It works immediately, needs no
setup, and is what the manual process already does — a DBA logs in with their own key and
does the work by hand. Carried into automation, it means the tool's access is the union of
its operators' access, which changes whenever somebody joins, leaves or changes team, and
which nobody has ever written down.

Two specific failures follow. A scheduled run — the kind Semaphore exists to make possible —
belongs to nobody in particular, so it borrows an identity from a person who may not be
there next quarter; when that person's key is revoked, the schedule breaks in a way that
takes a while to attribute. And the audit trail on the target says a human logged in, when
what actually happened was a tool acting on a request, which makes the log misleading
precisely where it matters.

The other easy option, a shared root password, is worse in every dimension and needs no
argument.

## Decision

Targets are reached by a dedicated technical account that exists for Basewright and for
nothing else. Not personal SSH keys, not a shared root password, not the operator's own
credentials forwarded through the automation.

Its properties:

- **Key-based authentication.** Its authorized keys are managed outside this repository, by
  whatever manages host accounts in the estate. Basewright consumes the account; it does not
  provision it, and it is not the source of truth for its access.
- **Privilege by escalation, not by being root.** The account escalates for the operations
  that need it. `host.privilege` is a preflight block: if the account cannot perform the
  required privileged operations, the run refuses at the gate rather than failing partway
  through an install.
- **Credentials come from the secret store at run time.** They are never in the inventory,
  never in the repository, and never in a plan. See
  [ADR-0007](0007-secrets-never-in-artifacts.md).
- **Authorisation lives in Semaphore.** Who may run which template against which inventory
  is Semaphore's RBAC, and the record of who asked is Semaphore's task history. See
  [ADR-0005](0005-semaphore-is-the-interface.md).

The identity that connects and the identity that authorised are deliberately different
things: the target's logs show the tool, and the task history shows the person who requested
the run. Both questions have an answer, and neither answer is a guess.

## Consequences

The tool's access is a stated, reviewable thing rather than an emergent property of the
current team roster. It can be audited, scoped, rotated and revoked on its own schedule, and
revoking it stops Basewright without stopping anybody's day-to-day access.

Scheduled and unattended runs work, because the identity does not belong to a person who
might be on leave. A person leaving the team does not silently break provisioning.

`host.privilege` as a block means a permissions problem surfaces before any change is made
rather than halfway through one, which is the difference between a refusal and a
half-configured machine.

The costs are ordinary operational ones. The account is a prerequisite: a host is not ready
for Basewright until the account exists and its key is installed, which is work for whoever
builds the machines. Its key needs rotation, and rotation has to be coordinated with the
secret store. And it is, by construction, an account that can install software and write to
`/etc` on every database host — a valuable target, which is why it is key-based, scoped to
the operations it needs, and separated from any human's day-to-day identity.

There is also a small loss of convenience: an engineer cannot debug a Basewright run by
simply running it as themselves, because their own key is not what the tool uses.

## Rejected alternatives

**Personal SSH keys, forwarded through the automation.** Zero setup, immediate. Rejected
because it makes the tool's access undefined and unstable, breaks unattended runs, and puts
a human's name on a target's audit log for an action a human did not take. It also means the
blast radius of one compromised laptop includes every database host.

**A shared root password in the secret store.** Simple, works everywhere, no per-host
account provisioning. Rejected because it removes the distinction between the tool and
anything else that has the password, cannot be scoped, and cannot be rotated without
coordinating with every consumer. Password authentication for automation is a step backwards
from keys regardless.

**One technical account per environment or per team.** More granular, and appealing where
production and development are strictly separated. Rejected as the default because
granularity here duplicates a boundary Semaphore's RBAC already draws, at the cost of more
accounts to provision and rotate. Nothing prevents an estate from doing it — the account
name is configuration — but the tool does not require it.

**A certificate authority issuing short-lived host certificates.** Better than static keys
on most axes. Not rejected on merit; it is out of scope, because the account's key material
is managed outside this tool by design. An estate that runs an SSH CA can supply this
account's credentials that way without Basewright knowing.

## Related

- [ADR-0007](0007-secrets-never-in-artifacts.md) — how the account's credentials reach a run.
- [ADR-0005](0005-semaphore-is-the-interface.md) — where authorisation and the record of who
  asked actually live.
- [ADR-0012](0012-starts-at-a-reachable-host.md) — the account existing is part of what
  "reachable" means.
