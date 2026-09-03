# ADR-0003: Humans choose the version, Basewright validates it

**Status:** Accepted · 2026-09-03

## Context

Every provisioning request has to settle on an engine version. Something has to decide
whether this machine gets 15 or 16, and the choice is not free: it is constrained upward by
what the OS can carry and what the vendor still packages, and downward by end-of-life dates
and by whatever the application on the other side has been certified against.

Some of those constraints are knowable from the machine and the vendor. Others are not. A
version is often chosen because an application vendor supports exactly that one, because the
rest of a replication topology already runs it, or because a migration is scheduled for next
quarter and this host has to match what exists today. None of that is visible from the host,
and none of it is inferable from a support matrix.

The tempting behaviour is to pick the newest supported version when the caller does not say.
It produces a good result most of the time and a surprising one occasionally — and the
occasional surprise lands on a machine that is now in production with the wrong major
version, which is expensive to undo.

## Decision

The version is an input. The caller states it, and Basewright validates that choice against
the profile's support matrix rather than making it.

The support matrix lives in `profiles/<engine>/support-matrix.yml` as data — engine version
against OS family, distribution, distribution version, architecture, with an end-of-life
date per version. Validation produces one of four outcomes:

- **Supported.** The combination is in the matrix, the version is the profile default, and
  end of life is far enough away. Nothing to say.
- **Supported with a warning.** The combination is in the matrix but the request is not the
  profile default (`version.not_default`), or end of life falls within twelve months
  (`version.eol`). The plan is produced, the warning is rendered into it, and it has to be
  acknowledged before apply will run.
- **Refused.** The combination is not in the matrix (`os.supported`, `arch.supported`).
  This is a block: no plan, and a refusal naming the requested version, the observed OS, and
  what the matrix does support.
- **Defaulted.** No version was requested, so the profile's `default_version` is used, and
  the plan records that the version was defaulted rather than requested.

The profile carries a default so a request with no version still produces a complete plan.
The default is a stated position in reviewable data, not an inference made at run time from
what happens to be newest.

## Consequences

The tool never silently installs a major version nobody asked for. Where a version came from
is recorded in the plan — requested explicitly, or defaulted — so the question is answerable
afterwards.

The constraints a human holds and the constraints a machine holds are handled by whichever
one has the information. Application certification and topology stay with the requester;
OS compatibility, architecture and end-of-life dates are checked mechanically, every time,
including on the fortieth host when nobody is paying close attention.

Keeping the matrix as profile data means an end-of-life date or a newly packaged
distribution version is a small, reviewable change that ships without touching the core, in
line with [ADR-0002](0002-engines-are-data.md).

The costs: the matrix is a maintenance obligation, and a stale one produces a refusal that
is Basewright's fault rather than the host's. Warnings that fire on every request — a
sensible default that is deliberately not the newest version, for instance — decay into
noise, so `version.not_default` has to stay genuinely informative or it will be acknowledged
without being read.

A refusal can also block work that would have succeeded, because an unlisted combination and
an unsupported one look identical from inside the matrix. That is the intended trade: the
fix is a reviewed change to the matrix, where somebody has to agree the combination is
actually supported, rather than an override at the console.

## Rejected alternatives

**Basewright picks the newest supported version.** Fewer inputs, fine most of the time.
Rejected because the cases where it is wrong are the expensive ones, and they are invisible
until the application fails to start on a database that is now in production. The tool
cannot see application certification, and pretending otherwise makes it confidently wrong.

**Accept any version the vendor repository offers, and warn if it looks unusual.** Maximum
flexibility. Rejected because it makes the support matrix advisory, and an advisory matrix
stops being maintained. It also means the first person to discover that a combination does
not work is whoever gets paged, rather than whoever ran preflight.

**Pin the version per environment in the inventory instead of per request.** Attractive
where an estate is uniform. Rejected as the primary mechanism because it moves the decision
somewhere less visible than the request, and the plan can no longer say whether a version
was chosen for this host or inherited from a group. Path overrides can still live in the
inventory; the version is deliberately part of what is asked for.

## Related

- [ADR-0002](0002-engines-are-data.md) — why the matrix is profile data.
- [ADR-0004](0004-two-severities-no-override.md) — why an unsupported combination is a block
  with no override.
- [ADR-0011](0011-native-packages-from-vendors.md) — what "available" means for a version.
