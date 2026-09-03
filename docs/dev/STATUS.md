# Status

What is actually merged, what is placeholder, and what is still missing. Kept accurate on
purpose: an overstated status section is the fastest way to lose a technical reader.

Last reviewed: 2026-09-03.

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
| CLI skeleton, no verb implemented                 | done        |
| Generated diagrams and terminal captures, checked in CI | done   |
| Architecture decision records 0001–0013           | not started |
| Profile JSON Schema                               | not started |
| Profile loader with schema validation             | not started |
| Fact model and normalization                      | not started |
| Gate engine and severity resolution               | not started |
| Planner: sizing evaluation, layout, plan assembly | not started |
| Report rendering, human and JSON                  | not started |
| Golden plan fixtures                              | not started |
| Plan determinism check in CI                      | not started |

## Not yet wired into CI

These belong in the pipeline described in the brief and are added when there is something
for them to check:

- `ansible-lint` — waits for the first playbook and role, in Phase A.
- `molecule` — waits for the first engine role, in Phase A.
- Profile schema validation — waits for the schema, in Foundation.
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
| Minimum cores, RAM and free space per path | placeholder — these become block thresholds |
| OS families in the estate                | assumed: Debian/Ubuntu first, then RHEL/Rocky  |
| Port convention                          | placeholder — engine default, single instance |

A block threshold has to be a number someone will defend in a review. Until these are
confirmed, they are documented as assumptions rather than presented as policy.

## Known gaps

- No verb of the CLI does anything yet; every one exits 69 and points here.
- No engine profile exists, so there is nothing for the schema to validate against.
- The quickstart in the README is deliberately absent rather than aspirational. The two
  terminal images it does carry are real captures of a tool that does not do anything yet.
- The plan rendering in the README is a specification of the artifact's shape, labelled as
  such, and is replaced by a generated capture once the planner produces one.
