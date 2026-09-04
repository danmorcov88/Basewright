# Status

What is actually merged, what is placeholder, and what is still missing. Kept accurate on
purpose: an overstated status section is the fastest way to lose a technical reader.

Last reviewed: 2026-09-04.

## Phases

| Phase          | Contents                                                    | Status      |
| -------------- | ----------------------------------------------------------- | ----------- |
| **Foundation** | Schema, loader, fact model, gate engine, planner, report, CI | in progress |
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
| Architecture decision records 0001–0015           | done        |
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
| `plan` and `verify`                               | not started |
| Planner: sizing evaluation, layout, plan assembly | not started |
| Report rendering for a plan, human and JSON       | not started |
| Golden plan fixtures                              | not started |
| Plan determinism check in CI                      | not started |

## Not yet wired into CI

These belong in the pipeline described in the brief and are added when there is something
for them to check:

- `ansible-lint` — waits for the first playbook and role, in Phase A.
- `molecule` — waits for the first engine role, in Phase A.
- Plan determinism — waits for the planner, in Foundation.
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
  then both verbs say so rather than implying a machine was contacted. `plan` and `verify`
  still exit 69 and point here.
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
- **The plan contract is not frozen.** `plan.json` carries `schema_version: "1"` and
  nothing has ever produced one, so it is still being written: the `host` section was
  reshaped alongside the fact model without a version bump, because bumping a contract
  with no second reader is ceremony. It freezes when `plan` produces its first artifact,
  and every change after that is a version.
- The fact model was built to be exactly what the shared gates need. Writing them found one
  gap, `reachable_repositories`, which is now in the contract; everything else the twenty
  rules ask for was already there.
- Facts a blocking rule needs are required by the contract; the ones only a warning reads
  may be absent. A host that does not report them gets that warning skipped, which is a
  reportable outcome rather than a guess.
- The quickstart in the README is deliberately absent rather than aspirational. Every
  terminal image it carries is a real capture, including the ones of verbs that do not
  work yet.
- The plan rendering in the README is a specification of the artifact's shape, labelled as
  such, and is replaced by a generated capture once the planner produces one.
