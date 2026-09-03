# ADR-0013: Backups are out of scope and belong to a separate tool

**Status:** Accepted · 2026-09-03

## Context

A database instance is not production-ready without backups, and the profile already knows
about a backup path — it plans one, sizes the free space requirement for it, sets its
ownership, and `verify` checks the service account can write to it. From there it is a very
short-looking step to scheduling a dump, and a shorter-looking one to keeping a few of them.

The step is short and the destination is not. Backup is not a feature; it is a system with a
different shape and a much longer life:

- **It is continuous.** Provisioning happens once per instance. Backup runs for the
  instance's entire life, which means scheduling, failure handling, alerting when a run does
  not happen, and someone to notice.
- **Its real product is restore.** A backup that has never been restored is a file. Proving
  it is more than that requires somewhere to restore into, a way to check the result, and a
  record of when it was last done. That is a control plane, not a cron entry.
- **It has its own retention, storage and compliance surface.** Where copies live, how long,
  encrypted how, deleted by whom.
- **It fails differently.** Provisioning fails loudly and immediately, on a machine nobody
  depends on yet. Backup fails silently, months in, and is discovered during a restore.

A provisioning tool that grows a backup feature tends to grow the easy half — take a dump on
a schedule — and stop there. That half is the part that produces false confidence: a green
task history, files accumulating, and no evidence anybody could restore from them. It is
worse than nothing, because it answers the question "do we have backups?" with a misleading
yes.

There is also a scope argument specific to this project. The tool is finishable because its
job ends at a verified instance. Backup would double it and change its character from a
thing that runs on request to a thing that runs forever.

## Decision

Backup scheduling, backup execution, retention management, restore and restore verification
are out of scope, permanently. This is not a phase that was deferred.

What Basewright does at the boundary, and no more:

- **Plans a backup path**, with its owner, mode and free-space requirement, so the instance
  is ready to be backed up by something else.
- **Blocks on `disk.free_space`** for that path, so an instance is not provisioned onto a
  host that cannot hold its backups.
- **Verifies `backup.writable`** — the service account can actually write there — so the
  handover to the backup system is on a foundation that was checked rather than assumed.

It does not install a backup agent, write a schedule, take a dump, manage retention, or
report on backup health.

A separate tool owns that side: a control plane that watches an instance for the rest of its
life and verifies that its backups are restorable. Two tools, one boundary, neither reaching
into the other's job. The boundary is a provisioned instance with a writable, correctly sized
backup path — which is precisely what `verify` proves.

## Consequences

Basewright stays finishable, and stays a request-driven tool rather than a service that has
to keep running.

The handover is a checked contract rather than an assumption. The backup system inherits a
path that exists, is owned correctly, is writable by the service account, and has space —
each of those asserted rather than hoped for.

Nobody can mistake this tool for backup coverage. There is no green task in its history that
could be read as evidence that the data is safe, which is the specific false confidence this
decision exists to prevent.

The costs are honest ones. A newly provisioned instance is not backed up, and there is a
window between provisioning and whenever the backup system picks it up — a real risk that has
to be handled by process, not by this tool. Two tools mean two things to deploy, learn and
operate. And the operator does have to go elsewhere to answer "is this instance protected?",
which is a worse experience than a single pane would be.

Accepting the split is a judgement that a clear boundary between two tools that each do their
job is worth more than one tool that does one job well and the other badly.

## Rejected alternatives

**Ship a minimal backup role: a dump on a schedule, a few kept copies.** Ninety percent of
the perceived value for a small fraction of the work, and it is what most provisioning tools
do. Rejected because it delivers the half that creates confidence and omits the half that
justifies it. An unrestored dump on a schedule invites everybody to stop thinking about the
problem.

**Install and configure a third-party backup agent, without owning the policy.** Narrower:
Basewright puts the agent on the host and registers the instance, and the backup product
handles the rest. Genuinely tempting, and not rejected on principle — it is rejected for now
because it makes this tool depend on a specific product's registration model and lifecycle,
which is a large coupling for a convenience. If an estate standardises on one, it can be an
optional role, and it will be a new decision that supersedes this paragraph rather than an
extension made quietly.

**Verify that a backup exists, without creating one.** Read-only, so it avoids owning the
schedule, and it would let `verify` report something about protection. Rejected because
verifying a backup properly means restoring it, and restoring it means somewhere to restore
into — which is the separate tool. A weaker check, such as the existence of a recent file,
is the false confidence again in a smaller package.

**Add backups later, once provisioning is finished.** The reasonable-sounding deferral.
Rejected as a *stated position*: recorded here as out of scope so the question is closed, and
so the boundary can be designed against rather than left ambiguous. If it is ever revisited,
it will be by superseding this record with an argument, not by an incremental feature that
nobody decided to add.

## Related

- [ADR-0012](0012-starts-at-a-reachable-host.md) — the same boundary drawn at the other end
  of the instance's life.
- [ADR-0001](0001-plan-before-apply.md) — `verify` proving the backup path is writable is
  what makes the handover a contract.
