# Status

What is actually merged, what is placeholder, and what is still missing. Kept accurate on
purpose: an overstated status section is the fastest way to lose a technical reader.

Last reviewed: 2026-09-04.

## Phases

| Phase          | Contents                                                    | Status      |
| -------------- | ----------------------------------------------------------- | ----------- |
| **Foundation** | Schema, loader, fact model, gate engine, planner, report, CI | complete    |
| **Phase A**    | PostgreSQL on Debian/Ubuntu, end to end                     | complete    |
| **Phase B**    | RHEL/Rocky, Semaphore templates, warning acknowledgement, plan storage | not started |
| **Phase C**    | A second engine, added without touching `basewright/`       | not started |
| **Phase D**    | Windows and SQL Server                                      | not started |
| **Phase E**    | Audit trail, plan diff against a live host, signed releases | not started |

## Foundation, in detail

| Item                                              | Status      |
| ------------------------------------------------- | ----------- |
| Repository skeleton, license, commit template     | done        |
| Engine-name guard over the core                   | done        |
| Generated diagrams and terminal captures, checked in CI | done   |
| Architecture decision records 0001–0025           | done        |
| Profile JSON Schema, and the plan contract        | done        |
| Profile loader with schema validation             | done        |
| Facts contract, typed model and normalization     | done        |
| `gather`, from a facts document                   | done        |
| `gather`, from a live host                        | done        |
| `reachable_repositories`, and the rule that reads it | done      |
| The collecting role, and its molecule scenario    | done        |
| `ansible-lint` and `molecule` in CI               | done        |
| `preflight`, from a facts document                | done        |
| Expression language, and its interpreter          | done        |
| Gate engine and severity resolution               | done        |
| The twenty shared rules of the brief              | done        |
| Refusal report, and the preflight contract        | done        |
| `plan`, from a facts document                     | done        |
| An engine profile, and `--engine` to name it      | done        |
| Planner: sizing evaluation, layout, plan assembly | done        |
| The plan contract, frozen                         | done        |
| Golden plan fixtures, and the refusals beside them | done       |
| Plan determinism check in CI                      | done        |
| Report rendering for a plan, human and JSON       | done        |
| Reading a plan back, and checking it is intact    | done        |
| Exit codes, as a documented and tested set        | done        |
| `apply`, and the roles that execute a plan        | done        |
| `verify`, and the role that reads an instance     | done        |

## The loop closes

Every verb in §4 of the brief is built, and the last of them is the one that makes the other
four worth anything: `apply` promised something, and `verify` reads the instance back and
says whether the promise held.

What CI does on every pull request is the whole of it. A bare `ubuntu:24.04` container is
read, gated, planned for, provisioned from its own plan, provisioned again with nothing left
to do, and verified. Then the scenario changes a parameter on the running instance behind
the plan's back and insists the tool goes red -- exactly `2`, and naming the parameter --
because a verify that only ever passes has been shown to agree with a correct instance and
nothing more.

Two things are still true and worth saying in the same breath. **The numbers in the profile
are upstream defaults rather than the estate's policy**, all seven of them, and the table
further down says which is which. And **the interface is missing**: `deploy/semaphore/` is
empty, so the four templates of §12 that would let anybody run any of this without a shell
are Phase B.

## Collecting from a live host

`gather` reads a real machine now. `ansible/playbooks/gather.yml` reaches the host, the
`gather` role reads it, and the document lands on the control node where the CLI reads it
straight back. The playbook is the entry point and the CLI never opens a socket
([ADR-0020](../adr/0020-the-playbook-is-the-entry-point.md)).

What is worth knowing about it:

- **Parsing is Python.** `basewright/facts/collect.py` turns what a machine printed into the
  contract document, and the role's template is one line long. Every sample the parsers are
  tested against came off a real host, because the failure this code has is not a crash --
  it is reading a line slightly wrong and handing the gate engine a machine that does not
  exist.
- **The collector enumerates; the profile decides.** Services come from
  `ansible.builtin.service_facts` and are reported whatever they are. A shared role that
  went looking for one service by name would be the same defect as a planner that branched
  on one, and the engine-name guard now scans shared roles for exactly that.
- **A host that cannot enumerate its services gets no document.** An empty list is what
  makes a conflict rule pass on a machine already running the thing being provisioned, so
  the role refuses rather than writing one that would be read as an all-clear.
- **A fact nobody could collect is absent, never invented.** A container with no message bus
  reports no `time_sync`; a host with no `ufw` reports no firewall. Absent means nobody
  asked, and the rule that wanted it skips and says so.
- **`reachable_repositories` is collected, and it is the one thing the collector is told
  about what is being provisioned.** Nineteen of the twenty shared rules ask about the
  machine alone. The twentieth asks whether the host can reach the repository its packages
  would come from, and where those come from is written in a profile -- so `gather.yml`
  takes `gather_engine` or `gather_profile`, probes the url that profile declares for this
  host's family, and writes down what answered
  ([ADR-0021](../adr/0021-the-collector-is-told-what-is-being-provisioned.md)). Without
  one, the question is not put and the fact is absent. The role still knows no engine by
  name: the urls come out of `basewright/facts/repositories.py` through a two-line filter,
  and the guard scans the role exactly as before.
- **The role is read-only, and that is asserted rather than hoped for.**
  `test/unit/test_gather_is_read_only.py` reads the tasks and fails on any module that
  could change the target, and on any command that does not declare it changed nothing.
  Molecule's idempotence check cannot do this job here: the document records the moment it
  was collected, so a second run writes a different file, and a collector producing
  byte-identical output would be lying about when it looked.
- **A container reports Docker's bind-mounted files as mounts.** `/etc/hostname` and its
  two neighbours really are mount points in a container, and the collector reports what the
  kernel says. Nothing chooses a data path there, and filtering them would mean the
  collector deciding which of a host's mounts are real.

Two of the fixture hosts are documents the playbook produced against real containers,
committed as they came off the run. `collected.json` was collected without naming an
engine, so it has no `reachable_repositories` at all; `asked.json` was collected with a
profile named, so it has one, and it is empty -- the fixture profile's repository is at a
name reserved by RFC 2606 and resolves nowhere, on any network. That empty list is what
the refusal capture in the README renders, and the molecule scenario proves the same thing
on a container rather than on a file. Every other fixture beside them was written by hand
to exercise a rule; these two are the only ones whose contents nobody chose, and they are
there so that "a collected host is a host like any other" is a test rather than a claim.

Running against real machines has found three defects no fixture would have. The first
host reported a hundred and nine services and `gather` rendered every name on a single
line two thousand characters wide; the summary now reports a count and spells the names
out only while they fit. The other two are below, under what a real host taught the
rules.

## What a real host taught the rules

Two rules were written against fixtures, agreed with every fixture, and were wrong about a
real machine. Both were found by pointing A1 at a container and reading the report.

**`locale.present` refused a host that had the locale.** `locale -a` prints the names the C
library stores, and it normalizes the codeset when it does: a locale generated as
`en_US.UTF-8` is listed as `en_US.utf8`, on every Debian and Ubuntu machine there is. The
rule compared the two strings for equality and blocked. This is the most expensive shape of
wrong available here -- a block, with no run-time override, against a host that had exactly
what was asked for -- and the fixtures could not have caught it, because a fixture was
written by somebody who knew which spelling they meant. The codeset is now compared in the
spelling the library reduces it to; the language and the territory are compared as written,
because `en_US` and `en_GB` are different locales rather than different spellings of one.

**A mount on a logical volume reported no storage type.** A mount names whatever was
mounted and the kernel describes what is underneath, and on LVM the two never agree:
`/dev/mapper/vg0-data` against a device the kernel calls `dm-0`. The lookup failed, the
fact came back absent, and two sizing rules read it -- so an estate running on LVM got no
plan at all. Resolving it through the filesystem's own uuid, against the `by-uuid` links
the kernel reports per device, settles every spelling at once and needs no naming
convention kept up to date. The kernel had already done the interesting part: a mapped
device reports itself non-rotational only when everything beneath it is, so reading `dm-0`
is reading the answer for the disks under it. The sample this is tested against is a real
one, off a real volume group over a loop device.

## Applying a plan

`apply` is a playbook, not a verb of the CLI, for the same reason `gather` is (ADR-0020).
It takes one input -- the plan -- and there is no second one. Four things have to be true
before it touches anything: the plan is a plan and this build understands its contract, it
has not been edited since somebody approved it, the host is still the machine it was built
from, and its warnings have been acknowledged.

The first two are one check, and it is the tool that made the plan doing it: `plan --from`
validates the document against the frozen contract and recomputes the digest its name is
taken over. A plan of a version this build does not implement and a plan somebody edited
are both refused there rather than by a second opinion written in YAML.

What is worth knowing about the rest:

- **The phases run in the order the plan lists its own changes.** `changes` is the list
  somebody read and approved, so executing it in a different order would be doing something
  other than what was approved. The shared role and the engine's role therefore interleave
  rather than running one after the other, and each is entered per phase. That was found by
  running it: a profile whose vendor package makes the service account -- which is most of
  them -- cannot have its directories owned before the packages are installed.
- **The engine's role is the only place the engine's name appears.**
  `ansible/roles/postgresql/` knows that a locale and an encoding are arguments to
  `pg_createcluster`, that a cluster has a start policy, and that a superuser has a password
  set over a local socket. `ansible/roles/common/` knows about accounts, directories and
  host settings, and nothing else. The playbook reads the engine out of the plan.
- **Apply reads the plan and one other thing: a template, by the name the plan gives it.**
  That is the whole exception, it is a file rather than a value, and every value poured into
  it comes from the plan (ADR-0022). `test/unit/test_apply_reads_the_plan.py` reads the task
  files and fails on a second one.
- **Nothing that handles a password is ever loud.** Ansible logs its own arguments, so a
  secret leaks not because somebody printed one but because nobody said not to. The
  statement that sets it goes in over stdin, dollar-quoted so there is nothing to escape,
  and a test asserts that every task touching the value is `no_log` and that none of them
  puts it in argv.
- **The secret store is a seam.** Semaphore's own store is the real target and arrives with
  the Semaphore templates in Phase B; a container needs one now. So the sink is chosen by a
  variable, there is one implementation -- a file on the control node, mode 0600, at the
  location the plan names -- and the second is a file beside the first rather than an edit
  to everything that calls it.
- **The packaging is told not to make a cluster nobody planned.** Installing the Debian
  server package creates a cluster of its own, with the locale, encoding and data directory
  the packaging chose. Since apply is never destructive there would be no putting that right
  afterwards, so a drop-in in `createcluster.d` turns it off before anything is installed.
- **initdb owns the inside of its data directory.** The shared layout phase creates every
  path the plan names, and on this engine one of them -- the write-ahead log, at the
  upstream default -- is inside the data directory, which initdb requires to be empty. The
  engine's role takes the empty placeholder away again immediately before, with `rmdir`
  rather than a recursive removal: `rmdir` refuses a directory with anything at all in it,
  so what was made minutes ago goes and anything holding data is left for initdb to refuse
  by name.
- **Idempotence is in the molecule sequence**, unlike the collecting scenario where it was
  deliberately dropped. A second run of the same plan reports zero changes, and that is the
  promise apply makes. The password is the interesting case: it is generated once by the
  store and read back on every run after, because rolling it would lock out whoever was
  given the first one -- and the statement that sets it runs only when the store had
  nothing.
- **The plan is produced in the scenario's prepare step rather than its converge step.** A
  plan is an input to apply, so making one is setting up the fixture; and a second plan
  against a host that now runs an instance would be refused by the conflict rule, correctly,
  so a converge that planned would fail its own idempotence check for the right reason.
- **A container is not a server, and its mount table is the difference that matters.**
  Ansible reads /etc/mtab and skips any line whose device is not a path, so a container's
  `overlay / overlay` is never reported -- which means every planned path is on no
  filesystem the host admits to having, and a blocking rule refuses the plan. That is the
  rule working. The scenario therefore makes the filesystems real: sparse images, looped and
  formatted, mounted where the plan places things, sized above the profile's floors so they
  clear them on any machine rather than on the ones that happen to have room.

### Drift, and what it cannot see

Apply re-reads the host and refuses one the plan no longer describes
([ADR-0023](../adr/0023-drift-is-measured-against-the-plan.md)). Identity -- the operating
system, the architecture, a filesystem's type and whether it spins -- must match exactly.
Capacity -- cores and memory -- drifts when it shrinks and not when it grows, because a host
that has been given more is still one this plan fits. A filesystem the plan placed a path on
and the host no longer reports is the loudest of them.

**Free space is deliberately not compared**, and it is the interesting omission: apply
consumes it, so a second run comparing against the plan's numbers would report its own work
as drift and refuse to be idempotent. It is checked once, by a blocking gate, before the
plan exists.

**Apply cannot notice an engine somebody else installed since the plan was made, or a port
taken since.** Neither is in the plan's host section, and apply reads the plan and nothing
else. Both are real gaps rather than oversights, they are named in `UNCHECKED` in
`basewright/drift.py`, and they are found later and less kindly -- the packaging refuses, or
the service fails to bind.

### The one job that depends on somebody else's server

This page used to say that everything else in CI ran offline. It does not, and the
correction is worth making rather than quietly softening: **every job needs the network.**
All eleven install from PyPI, and both molecule scenarios build their target images, which
means pulling from Docker Hub and installing systemd, python3 and a handful of tools from
the distribution's own archives. A page claiming otherwise was describing an intention.

What is true, and what the sentence was reaching for, is narrower. **The apply scenario is
the only job whose subject under test reaches a third party** -- it adds the vendor's
repository and installs from `apt.postgresql.org`, which is what the whole tool is for. So
it is the only job that can go red for a reason outside the control of GitHub, PyPI and the
distribution, all three of which CI already cannot start without.

That is stated rather than discovered, and it is why the collecting scenario proves its
refusal case against a name reserved by RFC 2606: `packages.example.invalid` resolves
nowhere on any network, so the case that refuses is free, deterministic, and does not add a
second job with a dependency on somebody else's uptime.

An apt cache or a local mirror between runs would remove that last dependency and is
deliberately not there. Adding it means a job that installs from a cache while the product
installs from a vendor, so the step being proved would no longer be the step that runs --
and `repo.reachable`, a blocking rule about whether a host can reach its repositories,
would be verified against something that is not one. An honest dependency is worth more
than a job that pretends not to have one.

## Verifying an instance

`verify` is a playbook, for the same reason `gather` and `apply` are (ADR-0020). An
engine's role puts eleven questions to the running instance, writes down what it said, and
`basewright verify` compares that document with the plan and renders the answer
([ADR-0024](../adr/0024-the-role-observes-and-the-core-judges.md)). Nothing under
`basewright/` opens a socket, and nothing under it knows what a cluster is.

What is worth knowing about it:

- **The observation is a document with a closed contract of its own**,
  `schema/observation.schema.json`. One shape for every engine, and the kinds give it its
  structure: `observations` is keyed by the eleven kinds a profile's checks may name, and
  each kind's shape is fixed. A kind missing from it was not observed, and absent is a
  different answer from empty here exactly as it is in a facts document.
- **The whole document comes from the engine's role, including the parts a shared role
  could have produced.** Asking systemd about a unit the plan names needs no engine, and
  neither does asking the kernel whether the service account can write to the backup path.
  They stay in the engine's role anyway: apply's split earns its keep because accounts and
  directories are identical work whichever engine asked, and asking whether a service is
  running is not -- for one engine it is a systemd unit, for another it could be several,
  and a shared role deciding which is a shared role that knows one engine from another. The
  argument, and the alternative, are in ADR-0024.
- **Engine knowledge is applied before the document is written, never after.** The role
  reduces a version string to its major part, asks for a byte count in bytes because the
  plan records one, and marks an authentication method as requiring a password or not --
  while the method's own name travels through untranslated, so the report names the rule
  somebody has to go and delete. What is left in the core is comparison.
- **The role asks its instance for JSON rather than printing something to be parsed.** One
  statement, one round trip, one object. `gather` parses what a machine printed because
  there is no alternative there; here there is, and taking it keeps a parser that would
  have had to know which server it was reading out of the core entirely. The one thing that
  genuinely is parsed -- the socket table -- has a parser in the core that takes the
  process name as an argument.
- **A check nobody could run is not a pass, and it refuses the run**
  ([ADR-0025](../adr/0025-a-check-nobody-could-run-is-not-a-pass.md)). This is the
  difference from preflight's `skip` and it is deliberate: preflight decides whether to
  proceed, and a rule about an uncollected fact is no reason to refuse a host. Verify makes
  a claim, and an unasked question contributes nothing to it. A cluster that is down
  produces one failure -- the service -- and seven unobserved, so the root cause stays
  visible and the verdict reads `UNPROVED` rather than `FAILED`.
- **A profile can narrow a kind, and can never excuse one.** The check's `expr` is
  evaluated only on a kind that already passed, so there is no expression a profile can
  write that turns a mismatch into a pass. The real profile uses it once: the `port` kind
  judges the port because the port is what the plan carries, and that this instance is
  bound to no address but loopback is the profile's own decision, written where somebody
  arguing with it would look.
- **The scenario's ten hand-written assertions are gone, replaced by a verify run.** They
  were the scenario checking its own work. Two are left and both are deliberate: that the
  secret is a 0600 file where the plan said, and that the plan's secret entry has nowhere
  to put a value. Neither is something a running database could be asked -- one is about
  the control node and the other about the artifact.
- **The proof is the failing case.** A verify that only ever passes has been shown to
  agree with a correct instance and nothing more. So the scenario runs `ALTER SYSTEM` on
  the live cluster to widen a parameter behind the plan's back, reloads, reads it again,
  and insists the verb exits **exactly** 2 and names the parameter. `ALTER SYSTEM` rather
  than an edit to the drop-in on purpose: it is what somebody in a hurry actually does, it
  survives a reload, and it is read after every configuration file, so it is the exact
  shape of the drift this exists to catch.

### What a real container taught this one

Two defects, both in the half that had to know the engine, and neither of a shape a fixture
could have had -- because a fixture is written by somebody who already knows what the answer
should be.

**A JSON string is not a SQL string literal.** The query that reads the planned parameters
back builds a list of their names, and the first version quoted them with `to_json` on the
reasoning that a JSON string is a quoted string. It is, everywhere except SQL, where double
quotes are an identifier -- so `"shared_buffers"` was a column the query did not have and
the cluster said so. What is worth recording is not the mistake but the report it produced:
the connection check failed with the server's own message, seven checks that needed the
connection came back unobserved, and the verdict named the one thing to fix. The check
being built was the check that found the bug in it.

**A start policy is a file with eight lines of explanation above it.** This packaging keeps
the cluster's start policy in `start.conf`, and reading the file and calling it the value
produced a failure report with the entire comment block quoted inside it -- correctly, since
the plan says `auto` and a paragraph of explanation is not `auto`. It is the first line that
is neither blank nor a comment.

### What verify does not prove

Three narrowings, all of them made while writing the judgements, and all of them changes to
what the profile's titles claim rather than gaps left unsaid.

- **The connection it proves is over the local socket, as the service account.** That is
  authentication -- by the operating system rather than by a password -- and it proves the
  instance is serving. It is not a password-authenticated connection over TCP, and proving
  that means verify reading the secret store, which arrives with the Semaphore templates.
- **The port kind judges the port and not the address**, because the plan carries no listen
  address to compare one against. The address is asked by the profile, as an expression, and
  a profile that did not ask would not have it checked. Putting a planned listen address in
  the plan would be a contract change and a version with it.
- **The account kind asks whether a password is set, not whether it is a good one.** §10 of
  the brief says "no default or empty administrative password", and observing the first half
  of that means guessing passwords against a live instance. A verification step that attacks
  the thing it is verifying is a worse idea than the gap it would close.

## Exit codes

Three, closed, and documented in [ADR-0019](../adr/0019-exit-codes-are-the-contract.md):
`0` yes, `2` no, `64` the request is malformed. They are a contract with Semaphore, which
marks a task red on anything non-zero, so what the number carries is what to do next rather
than that something failed.

The set lives in `EXIT_CODES` in `basewright/cli.py`. The README table and the diagram are
rendered from it, and `test/unit/test_cli.py` holds it in both directions: every code is
reachable from a real invocation, and the CLI returns nothing outside the set -- including
an AST scan that refuses a bare `return 2`, because the registry is only a contract while
every exit runs through a named constant.

**There were four.** `69` said the verb existed and was not built, ADR-0019 named it as the
one member with an expiry date, and it went when `verify` landed. A set that loses a member
is narrower than it was rather than different: nothing that read `0`, `2` or `64` has to
change, and there is now no invocation of this tool that can produce anything else. The
test that held the list of unbuilt verbs is still there, asserting the list is empty --
kept, rather than deleted with the list, because it is what would have to stop being true
for the code to be needed again.

## What CI proves, and what it does not picture

Both molecule scenarios run on every pull request. The second takes a bare container from
nothing to a running instance, over it again with nothing to do, verifies it, changes it,
and verifies it again expecting a refusal.

The one thing that is proved rather than pictured is `apply` itself. A run prints package
versions and moments, and neither survives a byte-for-byte image check, so there is no
capture of it and there deliberately never will be -- the scenario in CI is the proof, and
a diagram generated from the playbook is what the README shows instead. `verify` was held
to the same test and came out the other way: a report rendered from a committed reading is
deterministic and ASCII, so it is captured, and the readings it is captured from came off
the container that scenario provisioned.

## The first profile, and the seven values it had to assume

`profiles/postgresql/` ships. It is the first thing in this repository that describes a real
engine, and eight declarative files is all of it: nothing under `basewright/` knows the word
PostgreSQL, and a test scans every line to keep that true.

§21 of the brief names seven pieces of information that cannot be invented and have to come
from the team, and none of them has arrived. It also says what to do in the meantime: ship
reasonable upstream defaults, keep them in `profiles/`, and mark them here. That is what the
table below is. **Every row is an assumption, not a policy**, and every one of them is a
single value in a reviewable YAML file with the argument for it written beside it.

| §21 | What it needs | What ships, and why that |
| --- | ------------- | ------------------------ |
| 1 | Path conventions | The upstream Debian layout, exactly: `/var/lib/postgresql/<version>/<cluster>`, the log under `/var/log/postgresql`. Not a tidier scheme of our own, so that `pg_lsclusters` and the packaged logrotate keep working and a DBA finds things where every other cluster keeps them. |
| 2 | Service account | `postgres`, group `postgres`, home `/var/lib/postgresql`, shell `/bin/bash`. **Not created by Basewright**: the vendor package makes it, and an account made first would take whatever uid was free rather than the one the package's files are owned by. |
| 3 | Locale and encoding | `en_US.UTF-8` and `UTF8`, the locale in `profile.yml` because a shared rule blocks a host without it, the encoding in `apply.yml` because creating the instance is what consumes it. The locale is the one thing on this page a European estate is most likely to change; the encoding is the one nobody should. |
| 4 | Authentication rules | Loopback only, `scram-sha-256` everywhere, `peer` for the service account over the local socket, and no rule anywhere that grants access without a password. A new instance is reachable only from the machine it runs on; widening it is a decision somebody makes on purpose. |
| 5 | Minimum resources | 2 cores, 2 GB, and per path: data 20 GB, wal 10 GB, log 2 GB, backup 50 GB. **These are blocks with no run-time override.** They are floors rather than recommendations: a real production server clears all of them without noticing, and they exist to catch a request pointed at a machine nobody meant to provision. |
| 6 | OS families | Debian family only — Ubuntu 22.04 and 24.04, Debian 12. RHEL is Phase B, and declaring it before it is tested would be a claim rather than a fact. |
| 7 | Port convention | 5432, one instance per host. A per-instance allocation scheme would change `defaults.port` and nothing else. |

Two of those deserve a second look before anybody relies on them.

**The backup path is deliberately not `/var/backups`.** That is where the distribution keeps
a few kilobytes of dpkg state, and it lands on the root filesystem of every machine, so a
50 GB floor there would refuse almost every host for the wrong reason. The default is
`/backup/postgresql/<instance>` — a mount somebody provisioned on purpose — and a host that
has not got one is refused rather than quietly given the root filesystem. What the estate
actually calls that mount is the open question; that it is a mount is the assertion.

**The write-ahead log defaults to the upstream location inside the data directory**, so on
any host without a path override the profile warns that the two share a mount. That warning
is true, it is about the default rather than about the host, and acknowledging it is the
record that somebody looked. If the estate's convention gives the log its own mount, one
line in `layout.yml` changes and the warning stops.

### What the profile still cannot answer

- **`random_page_cost` and `effective_io_concurrency` read whether the data path is
  rotational, and a sizing rule that reads an unreported fact refuses the plan.** The
  refusal stands and it is deliberate: the alternative is a parameter quietly omitted, and
  PostgreSQL's own default of 4.0 is the wrong answer on every SSD. What has changed is
  which hosts fall into it. A mount on a logical volume is now resolved to the device the
  kernel describes, so an estate running on LVM — which is most of them — gets an answer
  rather than a refusal. What is left refusing is a host whose storage genuinely cannot be
  determined, and that is a smaller and more defensible set than it was.
- **The support matrix names three versions and their end-of-life dates.** They are
  upstream's published dates and they need re-reading whenever a release lands; a test
  fails the build if any of them has passed.
- **The templates are consumed now, and two things about them changed on the way.** They
  are rendered with the plan under a single name, `plan`, rather than with its sections
  spread across several -- one variable a template cannot reach past, and no chance of
  colliding with a name Ansible already uses. And the tuning template learned to write a
  byte count as a byte count: a plan records `8589934592` because that is the one spelling
  two steps can compare, and this engine has to be told the number is already in bytes
  rather than in whatever unit it would otherwise assume for the parameter.

## Known gaps

- `gather` and `preflight` read a facts document, and `verify` reads a plan and an
  observation. In every case a playbook is what produced the document and the CLI is what
  reads it, which is the split rather than a stage of it
  ([ADR-0020](../adr/0020-the-playbook-is-the-entry-point.md)).
- **`repo.reachable` reaches a verdict.** It was the last piece of A1 and it is done. The
  rule itself never changed — it was written in session 5 with both outcomes tested, and
  what was missing was a collector willing to ask. `gather.yml` now takes an optional
  engine or profile, probes the repository that profile declares, and writes down what
  answered ([ADR-0021](../adr/0021-the-collector-is-told-what-is-being-provisioned.md)).
  Absent still means nobody asked and still skips; present and empty means the host was
  asked and reached nothing, and blocks.
- `host.reachable` checks that the facts describe the host the request names. That a
  machine answered at all is settled by there being a document to read; what nobody notices
  going wrong is a plan built from another machine's facts, so that is what the rule checks.
- **One engine profile ships, and the fictional one stays.** `profiles/postgresql/` is
  real and `test/fixtures/profiles/exampledb/` is not, and both are put through the whole
  pipeline against the same five fixture hosts. The fictional one exercises the schema and
  the loader without implying anything about anybody's production database -- including the
  paths a real profile cannot use, and the two profiles it deliberately gets wrong. Keeping
  it is what stops the checks from only ever asking the questions one real engine happens
  to raise.
- **`verify.yml` gained the detail it was expected to gain.** It was the least settled of
  the profile files, its consumer was built in Phase A, and building it moved three things.
  The kind enum gained `initialization`, because the plan gained a section carrying the
  locale, the encoding and the checksum flag in session 11 and nothing read them back --
  and those three are the only promises on the whole plan that cannot be corrected in
  place. `expr` is consumed now, and the real profile uses it once. And two titles were
  narrowing claims rather than descriptions, so they are descriptions; both are under
  "What verify does not prove" above.
- **The plan contract is at version two, and the first version of it is why.** Reading
  `plan.json` against what an apply role would actually execute found it complete except
  for creating the instance: the locale lived in `profile.yml` and never reached the plan,
  the encoding and the checksum flag were nowhere at all, and nothing in `changes` said a
  cluster gets created. None of it was derivable, because apply reads the plan and nothing
  else. So the contract gained an `initialization` section and the version moved
  ([ADR-0022](../adr/0022-the-plan-says-how-the-instance-is-created.md)), on its own,
  before the role rather than inside it, with every golden regenerated as a diff somebody
  reads and every plan renamed because its content changed.

  The section is optional, and absent is a real answer: an engine whose packages leave a
  running instance behind them carries none, which is what the fictional profile's goldens
  now prove. The locale is not one of its settings -- it stays declared once in
  `profile.yml`, because a shared blocking rule reads it there and a second spelling would
  be a second thing to keep in step.

  Two smaller answers travel with it, and are open until apply exists to hold them: a
  configuration template is resolved by the filename the plan gives, under the profile the
  plan names, because rendering is not deciding when every value poured in comes from the
  plan; and a generated secret is written through one sink whose implementation is a role
  variable, so the path a password takes is identical under Semaphore and under a
  container.
- **The plan contract is frozen, and moving it is what a version is for.** `plan` produces
  artifacts, fourteen of them are committed under `test/golden/`, nested by engine, and
  every change to `plan.json` is a version of the contract rather than a patch -- which is
  what happened above, once, deliberately, and with the diff to show for it. What it
  gained on the way in: `parameters` carry a
  canonical value, a unit and a display rather than one rendered string (ADR-0016);
  `packages`, `configuration` and `tunables` are first-class sections, so apply can
  execute the plan without reading the profile (ADR-0018); `result` counts the warnings
  that need acknowledging; and a gate result names its source, so the plan and the
  preflight document describe a rule identically.
- **`warn_above` produces a warning that has to be acknowledged.** It is not a gate —
  preflight closed before the parameter existed — so it travels on the parameter as
  `above_advisory` and joins the same single count apply refuses on. There is one
  acknowledgement, because a warning raised after the gates closed is not a lesser warning.
- **A sizing rule that reads an unreported fact refuses the plan.** Not a defect in the
  profile and not a host that fell short: nobody can tell, so there is no value to write
  down and no plan. The alternative — omitting the parameter — is a hole apply would find
  halfway through, on somebody else's machine.
- **`apply.yml` is the eighth profile file.** `changes` and `secrets` needed data no file
  declared: which configuration files get written and where, which host settings get
  changed, and what secrets exist. Inferring any of it would have meant the core guessing
  at engine knowledge, so it is declared instead (ADR-0018). An `initialization` section
  was deliberately absent until apply existed to consume one; it is now known to be
  needed, and what it costs is below.
- **Two fixture hosts produce a plan and three are refused.** `rocky` and `small` are
  blocked by the support matrix, `crowded` by four rules at once. That ratio is the
  fixtures doing their job, and the refusals are committed as goldens for the same reason
  the plans are: a change that quietly stops refusing a host is the change most worth
  noticing.
- The fact model was built to be exactly what the shared gates need. Writing them found one
  gap, `reachable_repositories`, which is now in the contract; everything else the twenty
  rules ask for was already there.
- Facts a blocking rule needs are required by the contract; the ones only a warning reads
  may be absent. A host that does not report them gets that warning skipped, which is a
  reportable outcome rather than a guess.
- **The quickstart is a quickstart now.** It said in its own first line that it was not
  one, for four sessions, because there was no engine to provision and no loop to walk
  through. Both exist. It runs every verb against documents committed under `test/`, every
  terminal image is a real capture of the command printed above it, and a test holds the
  two together so what a reader copies is what made the image.

  Two of those documents are readings of a container this repository's own test run
  provisioned, committed as they came back: `test/fixtures/plan/applied.json` is the plan
  the scenario built and applied, and `test/fixtures/observations/observed.json` is what
  the instance said afterwards. The same treatment `collected.json` got in session 9, and
  for the same reason -- a run prints package versions and moments, so the capture is made
  from a committed reading rather than from a live one.

- **`--profile` takes a path, and it is not going away.** `--engine NAME` looks one up
  under `profiles/`, and the two are mutually exclusive. Naming a directory stays how a profile author runs an uncommitted profile and
  how every fixture here is driven, so the change is additive and nobody has to plan around
  a removal.

- **Coverage has a floor of 95%.** Set at the number the suite actually reaches rather than
  comfortably below it, so a change that leaves new code unexercised fails in the pull
  request instead of in a review. The cost is real and is accepted: a refactor that deletes
  well-tested code can trip it, and the answer to that is to bring the tests along, which is
  the behaviour the floor exists to produce.
- **The plan rendering in the README is a real capture.** The specification block that
  stood there from the first commit is gone. The rendering is produced by
  `plan --from`, against a golden plan whose moment is pinned, because a plan produced
  from facts records when it was produced and a clock cannot be compared byte for byte.
  That the pipeline still produces the plan correctly is proved by rendering the goldens
  twice and diffing the bytes, which is a stronger check than a picture of one run.
- **The report renders the document, not the objects that built it.** Verify reads
  `plan.json` back off a disk months later, so there is one rendering and it works from
  the artifact. `plan --from` is what proves that rather than asserting it.
- **`plan --from` checks the plan is intact.** A plan is named after a digest of its own
  content, so the name is a checksum too. A file whose id no longer matches what it says
  has been edited since it was produced, and it is refused rather than rendered as though
  it were the artifact somebody approved. Retrieval by plan id, rather than by path, needs
  a plan store and is Phase B.
