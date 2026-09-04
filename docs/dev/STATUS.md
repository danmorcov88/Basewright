# Status

What is actually merged, what is placeholder, and what is still missing. Kept accurate on
purpose: an overstated status section is the fastest way to lose a technical reader.

Last reviewed: 2026-09-04.

## Phases

| Phase          | Contents                                                    | Status      |
| -------------- | ----------------------------------------------------------- | ----------- |
| **Foundation** | Schema, loader, fact model, gate engine, planner, report, CI | complete    |
| **Phase A**    | PostgreSQL on Debian/Ubuntu, end to end                     | not started |
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
| Architecture decision records 0001–0018           | done        |
| Profile JSON Schema, and the plan contract        | done        |
| Profile loader with schema validation             | done        |
| Facts contract, typed model and normalization     | done        |
| `gather`, from a facts document                   | done        |
| `gather`, from a live host                        | Phase A     |
| `preflight`, from a facts document                | done        |
| Expression language, and its interpreter          | done        |
| Gate engine and severity resolution               | done        |
| The twenty shared rules of the brief              | done        |
| Refusal report, and the preflight contract        | done        |
| `plan`, from a facts document                     | done        |
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

- `ansible-lint` — waits for the first playbook and role, in Phase A.
- `molecule` — waits for the first engine role, in Phase A.
- Quickstart output assertions — wait for a working end-to-end path, in Phase A.

## Placeholder values

Nothing here is settled. Each of the following will ship as a defensible upstream default in
`profiles/`, clearly marked, until the real convention arrives from the estate. They are
listed because a reader is entitled to know which numbers were chosen and which were
inherited.

| Input                                | Current state                                     |
| ------------------------------------ | ------------------------------------------------- |
| Path conventions: data, WAL, log, backup | placeholder, upstream-flavoured defaults      |
| Service account name, uid policy, shell  | placeholder                                   |
| Locale and encoding for `initdb`         | placeholder                                   |
| Default host-based authentication rules  | placeholder                                   |
| Minimum cores, RAM and free space per path | placeholder — `minimums` in `requirements.yml`, and `min_free` per path |
| Preferred filesystems, huge pages, swappiness | placeholder — `preferences` in `requirements.yml` |
| What counts as a conflicting installation | placeholder — `conflicts` in `requirements.yml` |
| OS families in the estate                | assumed: Debian/Ubuntu first, then RHEL/Rocky  |
| Port convention                          | placeholder — engine default, single instance |

A block threshold has to be a number someone will defend in a review. Until these are
confirmed, they are documented as assumptions rather than presented as policy.

## Known gaps

- `gather` and `preflight` read a facts document. Collecting those facts from a live host
  runs over SSH or WinRM, which is Ansible's half of the split and lands in Phase A. Until
  then both verbs say so rather than implying a machine was contacted. `verify` exits 69
  and points here.
- **`repo.reachable` always skips today.** It reads `reachable_repositories`, a fact that
  says which package repositories the host answered from. Which ones to try comes from the
  profile, so it is the one fact whose collection depends on knowing what is being
  provisioned, and it is collected by the gather playbook in Phase A. Absent means nobody
  asked and the rule skips; present and empty means the host was asked and reached nothing,
  which blocks. The rule is written, both outcomes are tested, and nothing about it changes
  when the collector starts answering.
- `host.reachable` checks that the facts describe the host the request names. That a
  machine answered at all is settled by there being a document to read; what nobody notices
  going wrong is a plan built from another machine's facts, so that is what the rule checks.
- No engine profile exists. `profiles/` is empty, so the schema job in CI walks it and
  says so rather than passing quietly. What exercises the schema today is a fixture
  profile for a fictional engine, under `test/fixtures/profiles/`, which is deliberately
  not parked in `profiles/` where it would make this page read better than it should.
- `verify.yml` is the least settled of the seven profile files. Its consumer is the verify
  step, built in Phase A, and its schema is expected to gain detail there.
- **The plan contract is frozen.** `plan` produces artifacts, five of them are committed
  under `test/golden/`, and every change to `plan.json` from here is a version of the
  contract rather than a patch. What it gained on the way in: `parameters` carry a
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
  is deliberately absent until apply exists to consume one.
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
