# ADR-0020: The playbook is the entry point, and the CLI reads documents

**Status:** Accepted · 2026-09-04

## Context

Until now every verb read a file. `gather --facts`, `preflight --facts --profile`,
`plan --from` — all of them take a path, and the facts they read were written by hand into
`test/fixtures/hosts/`. That was honest while nothing could reach a machine, and it stops
being an option the moment something can.

So the question that has been deferred since the first commit has to be answered: when
Basewright collects facts from a live host, what runs first?

There is an obvious answer, and it is what most tools in this space do. `basewright gather
--host db-01` looks like the right command. It is one entry point, one thing to document,
one thing to put in a runbook. Underneath, it shells out to `ansible-playbook`, or embeds
the Ansible API, and hands the operator back a rendered report.

The pull towards it is real, and it comes from a good instinct: a person should not have to
know which half of the tool does what. But it puts the CLI in charge of reaching machines,
and everything follows from that. The CLI grows connection handling, host key policy, retry
behaviour, a way to pass an inventory, a way to pass a vault password, and a way to report
that seventeen of twenty hosts answered. Each addition is small and each one is reasonable.
Together they mean the part of this project that is supposed to be a pure function of a
document is now a network client, and the tests that made it worth trusting need a network
or a mock of one.

There is a second reason, less about taste. Semaphore is the interface (ADR-0005), and
Semaphore runs playbooks. Four templates were specified in the brief, one per verb. A CLI
that invokes Ansible would mean Semaphore running a playbook that runs a CLI that runs
Ansible, which is not an architecture anybody would choose on purpose.

## Decision

**The playbook is the entry point. The CLI reads documents and never reaches a machine.**

`ansible/playbooks/gather.yml` is what Semaphore runs and what a person runs. It reaches
the host, reads it, writes `facts.json` on the control node, and then invokes
`basewright gather --facts` locally over the document it just wrote. Every verb that
touches a host follows the same shape as it arrives.

**`--facts PATH` does not change, and the contract does not move.** The document a
playbook writes and the documents committed under `test/fixtures/hosts/` are the same kind
of thing, read by the same code. That is the property worth having: a fixture is not a
simulation of a collected host, it *is* a collected host with the collection step done
earlier.

**Parsing is Python; running commands is Ansible.** What a machine printed is read by
`basewright/facts/collect.py` and reached from the role through one filter plugin that is
a two-line bridge. The role's template is a single line, because assembling the document
is a decision about what a host is and decisions are not made in Jinja (ADR-0008).

**The collector validates by being read.** The last thing the role does is run the CLI over
the document. There is no second copy of the schema in Ansible, and no way for the two to
drift: if the core would refuse the document, the playbook fails on the spot rather than
three steps later when somebody wanted a plan.

## Consequences

The CLI stays a pure function of its inputs, and its tests stay a suite that runs in three
seconds with no network. That is the whole reason the split exists, and it is the thing
that would have been given away first.

An operator has one command per verb, and it is a playbook. That is a slightly worse
first-run experience than a single binary that does everything, and it is the correct trade
for a tool whose interface is Semaphore rather than a terminal. The runbook in Phase B is
where that experience gets written down properly.

The control node needs Basewright installed, because the playbook invokes it. This is not a
new dependency — it is the same machine that renders the plan and the same install that
already had to exist — but it does mean the collection step cannot be run from a machine
that only has Ansible on it.

A facts document is a real artifact with a real path, which somebody has to decide where to
keep. For now the role writes it beside the checkout and says so. Durable storage and
retrieval by name is the same problem as plan storage, and it is deferred to the same phase.

The one thing this arrangement gives up is the ability to collect facts without Ansible at
all — for a host reachable some other way, or in a test that wants to exercise collection
end to end without a container. Nothing needs that today, and if something does, the answer
is another entry point writing the same document rather than a second definition of what a
document is.

## Rejected alternatives

**`basewright gather --host db-01`, shelling out to `ansible-playbook`.** One command, one
thing to document, and what a person would guess. Rejected because it makes the deciding
half of the tool a network client. Every property that makes the planner reviewable —
deterministic, offline, testable in isolation — depends on it not knowing how to reach a
machine, and the first `--ssh-common-args` would be the end of that.

**Embed the Ansible Python API in the CLI, rather than shelling out.** Tidier than
subprocess management, and it keeps error handling in one language. Rejected for the same
reason and one more: it makes ansible-core a hard runtime dependency of the wheel, so
`pip install basewright` on a laptop to read a plan would pull in a control node.

**Have the playbook write raw Ansible facts, and add a normalizing verb to the CLI.** It
would keep every line of parsing in Python, which is the part of this decision worth
keeping. Rejected because it makes the contract a second-class artifact: the thing the
playbook writes would no longer be the thing the fixtures are, and `--facts` would take two
different shapes depending on where the file came from. The contract only works as a
boundary if there is exactly one document.

**Shape the document in the role's template.** No filter plugin, no bridge, one fewer
moving part. Rejected because it puts a couple of hundred lines of parsing and assembly in
Jinja, where the only way to test it is to run a playbook against a container — so the
edges never get tested, and the edges are where a collector is wrong. Logic written in a
template because a template was already open is the defect ADR-0008 exists to prevent, and
it does not stop being one for being small at the time.

**Validate the document in the role, against the schema, with a YAML-native validator.**
Removes the dependency on the CLI at collection time. Rejected because it is a second
implementation of what a valid document is, living where the first one cannot see it. The
core refusing to read the document is the strongest statement available that the collector
and the contract still agree.

## Related

- [ADR-0008](0008-python-decides-ansible-acts.md) — the split this applies to the first
  thing that reaches a machine.
- [ADR-0005](0005-semaphore-is-the-interface.md) — who runs the playbook, and why there is
  no wrapper above it.
- [ADR-0002](0002-engines-are-data.md) — why the collector enumerates services rather than
  looking for one.
- [ADR-0012](0012-starts-at-a-reachable-host.md) — the host is already there; this is the
  step that finds out what it is.
