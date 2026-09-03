# ADR-0012: Basewright starts at a reachable host

**Status:** Accepted · 2026-09-03

## Context

The manual work this tool replaces begins at a specific point. The infrastructure team
builds the VM — hypervisor or cloud, network, storage, DNS, base image, the technical
account — and hands over an IP address. Everything after that is the database team's, and
everything after that is what is undocumented and different every time.

That handover is a real organisational boundary, not an arbitrary one. Different team,
different tools, different change process, different on-call. Terraform, vSphere, a cloud
API and an IPAM already own the left-hand side, and they own it competently.

The temptation to cross it is constant and reasonable-sounding. Provisioning would be
smoother end to end if one command created the VM and installed the database. It would demo
better. And each individual step across the line looks small: just create the disk, just add
the DNS record, just size the VM to fit the engine.

What follows from crossing it is not small. Creating a VM means credentials for the
hypervisor or the cloud, a model of networks and storage classes and placement, and an answer
to what happens when creation half-succeeds. It means owning the lifecycle — if the tool
creates infrastructure, somebody will expect it to destroy infrastructure — and destruction
is where the expensive mistakes live. It also means the tool's blast radius stops being "a
database is misconfigured" and becomes "a machine was deleted".

## Decision

Basewright starts at a host that already exists and is reachable, and stops at a verified
database instance on it.

Out of scope, permanently: creating or modifying virtual machines, networks, subnets,
firewalls as infrastructure objects, block storage, filesystems as provisioned volumes, DNS
records, load balancers, or cloud resources of any kind. Basewright does not call a
hypervisor or a cloud API.

What "reachable" means is precise, and it is the contract with whoever builds the machine:

- The host answers on SSH or WinRM at the address given.
- The dedicated technical account exists and can authenticate
  ([ADR-0006](0006-dedicated-technical-account.md)).
- That account can perform the required privileged operations — `host.privilege`.
- The mounts the plan will use exist, with the free space the profile requires. Basewright
  creates *directories* on existing filesystems; it does not create filesystems.

Each of those is a preflight block. A host that is not ready is refused with the specific
reason, which makes the refusal a useful message back across the boundary rather than a
failure.

Managed cloud databases are excluded by the same logic from the other direction: RDS, Azure
SQL and Cloud SQL are created by their providers' APIs and have no server to inspect, so
there is nothing for `gather`, `preflight` or `verify` to do.

## Consequences

The tool has one job and a bounded blast radius. The worst outcome of a bug is a
misconfigured database on a machine that already existed. Nothing in this repository can
delete a virtual machine, because nothing in it can talk to a hypervisor.

The scope stays small enough to finish, which is the difference between a working tool and a
platform that is perpetually eighty percent done.

The boundary is also what makes the tool composable. A pipeline can run Terraform and then
Basewright, and the interface between them is an IP address and an account — small enough to
be stable.

The refusals become a specification. "Refused because `/backup` has 12 GiB free and this
profile requires 100 GiB" is a precise, actionable message to the team that built the
machine, and it arrives before anybody has spent an afternoon on the install.

The costs are real. Provisioning is two steps run by two teams, and somebody has to
coordinate them. When a host is refused, the fix belongs to another team and their queue,
which is slower than fixing it in place. And the tool cannot right-size a machine for the
engine it is about to install — it can only say the machine is too small, and say it after
the machine was built.

That last one is the sharpest cost, and it is accepted: sizing a VM is a decision about
budget, capacity planning and placement, made by the people who own the platform, using
information this tool does not have.

## Rejected alternatives

**Create the VM too, at least for the common cloud cases.** One command, end to end, and a
better demo. Rejected because it means hypervisor and cloud credentials, a model of every
platform's networking and storage, an answer for partial creation, and eventually a deletion
path. It multiplies the risk and the scope for a convenience that a pipeline already
provides by running two tools in order.

**Create filesystems and mounts when they are missing.** A narrower crossing, and tempting:
`disk.free_space` refusals would often be fixable in place. Rejected because partitioning and
mounting are destructive operations on shared storage, and because the mount layout is a
capacity decision owned by whoever provisions storage. Creating directories on filesystems
that exist is the safe half, and it is where the line is drawn.

**Manage DNS records for the new instance.** Small, useful, and it is genuinely annoying to
do separately. Rejected because DNS is estate infrastructure with its own authority,
approval path and blast radius, and "just one record" is how a tool acquires credentials for
a zone.

**Support managed cloud databases as another engine profile.** Superficially it fits — an
engine, a version, some parameters. Rejected because the model does not hold: there is no
host to gather facts from, no filesystem layout, no preflight that means anything, and
sizing is an instance-class choice rather than a computation over hardware. Four of the five
verbs would be empty, which is the sign that it is a different tool.

## Related

- [ADR-0006](0006-dedicated-technical-account.md) — the account is part of the contract for
  "reachable".
- [ADR-0004](0004-two-severities-no-override.md) — an unready host is refused, not worked
  around.
- [ADR-0013](0013-backups-are-out-of-scope.md) — the same boundary drawn on the other end of
  the instance's life.
