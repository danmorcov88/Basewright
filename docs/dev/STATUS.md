# Status

What is actually merged, what is placeholder, and what is still missing. Kept accurate on
purpose: an overstated status section is the fastest way to lose a technical reader.

Last reviewed: 2026-09-04.

## Phases

| Phase          | Contents                                                    | Status      |
| -------------- | ----------------------------------------------------------- | ----------- |
| **Foundation** | Schema, loader, fact model, gate engine, planner, report, CI | complete    |
| **Phase A**    | PostgreSQL on Debian/Ubuntu, end to end                     | A1 and A2 done, A3 and A4 open |
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
| Architecture decision records 0001–0022           | done        |
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
| `verify`                                          | Phase A     |

## Foundation closes with a verb that is not built

`verify` reads a live instance and compares it to the plan it came from. Reaching a live
instance runs over SSH or WinRM, which is Ansible's half of the split, so there was no
version of this that could have been built in Foundation. It is listed as Phase A above
rather than as not started, because nothing about it is undecided — §10 of the brief says
what it checks, `verify.yml` is the profile file that carries the assertions, and what is
missing is a machine to ask.

It exists as a verb, it declares no flags, it exits `69`, and it names the page that says
so. An unbuilt verb declaring flags no implementation will read would be the same class of
claim as a screenshot of behaviour that does not exist, so its flags arrive with it.

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

## Exit codes

Four, closed, and documented in [ADR-0019](../adr/0019-exit-codes-are-the-contract.md):
`0` yes, `2` no, `64` the request is malformed, `69` the verb is not built. They are a
contract with Semaphore, which marks a task red on anything non-zero, so what the number
carries is what to do next rather than that something failed.

The set lives in `EXIT_CODES` in `basewright/cli.py`. The README table and the diagram are
rendered from it, and `test/unit/test_cli.py` holds it in both directions: every code is
reachable from a real invocation, and the CLI returns nothing outside the set. `69` is the
one member with an expiry date, and it goes when `verify` lands — which narrows the set
rather than changing it.

## Not yet wired into CI

These belong in the pipeline described in the brief and are added when there is something
for them to check:

- `molecule`, for an engine role — the collecting role has a scenario and it runs on every
  pull request. An engine's own role has nothing to test yet.
- Quickstart output assertions — the commands the README shows are held against the
  commands that produced its pictures, which is as much as can be asserted while there is
  no engine to provision. The rest waits for a working end-to-end path.

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
- **The templates are written and nothing consumes them yet.** `apply` is A3. They are here
  because the loader requires every named template to exist, and because writing them after
  seeing what apply happened to do would not be a specification.

## Known gaps

- `gather` and `preflight` both read a facts document, and the playbook is what writes one
  from a live host. `verify` is the verb that still has nothing behind it: it exits 69 and
  points here.
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
- `verify.yml` is the least settled of the seven profile files. Its consumer is the verify
  step, built in Phase A, and its schema is expected to gain detail there.
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
- **The quickstart in the README is not a quickstart, and says so in its first line.**
  There is no engine to provision, so what it walks through is the three verbs that work,
  against the fixtures under `test/`. Every terminal image it carries is a real capture,
  including the one of the verb that does not work yet. Each command is shown as
  copy-pasteable text above the picture it produced, and a test holds the two together, so
  what a reader copies is what made the image. It becomes a quickstart when Phase A gives
  it a host and a profile — not before, and it will not pretend otherwise in the meantime.

- **`--profile` takes a path, and it is not going away.** `--engine NAME`, looking one up
  under `profiles/`, is added when the first profile lands, and the two are mutually
  exclusive. Naming a directory stays how a profile author runs an uncommitted profile and
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
