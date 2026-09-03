# ADR-0011: Native packages from vendor repositories; never build from source

**Status:** Accepted · 2026-09-03

## Context

An engine has to arrive on the host somehow. The options are the distribution's own
packages, the vendor's repository, a tarball unpacked into `/opt`, a compile from source, or
a container.

Each has a following, and the arguments are familiar. Distribution packages are the most
integrated and the most conservative — Ubuntu 24.04 ships one PostgreSQL major version, and
it will not be the one wanted in two years. Vendor repositories carry current majors,
packaged the same way, with the same service units and file layout. Tarballs and source
builds give exact control over version and compile flags, at the price of owning patching,
init integration and dependency management forever. Containers are a different deployment
model, not a different packaging choice, and they change what "the host" means.

The decision matters more here than it would in a one-off install, because this tool exists
to do the same thing on the fortieth server as on the first. Whatever is chosen is chosen
forty times, and its maintenance cost is paid forty times.

There is also a direct interaction with the rest of the design. `verify` compares a running
instance to its plan; `version.matches` and `service.running` are only meaningful if the
service is a normal, predictable unit. The support matrix in
[ADR-0003](0003-humans-choose-the-version.md) is a claim about what is *available*, which
needs a repository to be a claim about. And the whole premise of the project is that
installation is the mechanical step at the end — which is only true if installation is boring.

## Decision

Engines are installed as native packages, from the distribution's repositories or the
vendor's official ones. Vendor repositories are preferred where they exist, because they
carry the versions the support matrix promises.

No compiling from source. No unpacking a tarball into `/opt`. No downloading a binary from
a URL that is not a package repository.

Each profile declares its packaging in `profiles/<engine>/packages.yml`: repository
definitions and signing keys per OS family, package names, and service names. Like everything
else engine-specific, it is data ([ADR-0002](0002-engines-are-data.md)).

Two rules attach to it:

- **`repo.reachable` is a preflight block.** If the host cannot reach the repository the
  plan depends on, the run refuses at the gate rather than failing partway through an
  install. Estates with an internal mirror point the profile at the mirror; the check is
  identical.
- **Repository keys are verified.** Adding a repository means adding its signing key, and
  package signature verification is not disabled. A repository added without key
  verification is a supply chain decision made silently, and this tool does not make one.

## Consequences

Installation is boring, which is the point. Packages handle dependencies, place files where
the OS expects them, install a service unit that behaves like every other service unit, and
integrate with the distribution's tooling. Everything downstream — `service.running`,
`port.listening`, `version.matches` — has a predictable thing to assert against.

Patching stays with whoever patches the estate. A security update for the engine arrives
through the same channel as every other update, on the same schedule, applied by the same
people. This tool provisions; it does not become the reason a host has an unpatched database
on it.

The plan can honestly say what will be installed, by name and version, before anything
happens — which it could not for a source build whose result depends on what the compiler
and the available headers produce on the day.

The costs are genuine. Only what the vendor packages can be installed: no unusual compile
flags, no patched build, no version that exists upstream but not in a repository. An engine
with no packages for a required OS family cannot be supported until it has some — the
profile schema will express the packaging, and the honest answer will be that the
combination is unsupported.

The tool also depends on repository availability at apply time, and on the vendor's
packaging remaining stable. `repo.reachable` turns the first into a refusal rather than a
half-install; the second is a maintenance obligation on the profile.

Adding a third-party repository is itself a trust decision. Restricting it to official
vendor repositories, declared in reviewable profile data with their keys, keeps that decision
visible and reviewable rather than buried in a task.

## Rejected alternatives

**Distribution packages only.** Maximally conservative, no third-party trust, no extra
repository to reach. Rejected because it makes the available version a function of the OS
release date. An estate on Ubuntu 22.04 could not be given a current major version, and the
support matrix would be dictated by the distribution rather than by what the team needs.

**Build from source, for exact control over version and flags.** The right answer for a
small number of specialists with a specific need. Rejected here because it transfers
patching, service integration, dependency management and reproducibility onto this project
permanently, and because it makes every host's installation a slightly different artifact.
It is the opposite of "identically on the fortieth server".

**Tarball into `/opt`, managed by the tool.** Avoids compilation, keeps version control, and
is how several vendors ship. Rejected because it means owning the service unit, the user, the
paths, the upgrade path and the patch process by hand, and because it puts the engine outside
the package database — so nothing else in the estate knows it is there.

**Containers.** A defensible way to run a database and a genuinely different deployment
model. Rejected because it is out of scope: this tool starts at a host the infrastructure
team already built and turns *that host* into a database server
([ADR-0012](0012-starts-at-a-reachable-host.md)). Provisioning a container platform is a
different problem with a different boundary.

## Related

- [ADR-0003](0003-humans-choose-the-version.md) — the support matrix is a claim about what
  the repositories carry.
- [ADR-0002](0002-engines-are-data.md) — packaging is profile data.
- [ADR-0012](0012-starts-at-a-reachable-host.md) — why containers are a different problem.
