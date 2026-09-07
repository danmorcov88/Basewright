# ADR-0024: An engine's role observes the instance; the core judges what it read

**Status:** Accepted · 2026-09-04

## Context

`verify` reads a running instance back and compares it to the plan it came from. Two
constraints meet here and they pull in opposite directions.

**Reaching a live instance runs over SSH, and the deciding half of this project does not
open sockets** ([ADR-0020](0020-the-playbook-is-the-entry-point.md)). That settles where
the reading happens: in Ansible, against the host, as an act rather than a decision.

**The core never branches on an engine name.** That settles where the judging happens:
under `basewright/`, where a test scans every line to keep an engine's name out of it.

What is not settled by either is the thing in between. §10 of the brief names ten checks —
service, port, connection, version, parameters, paths, log, backup, auth, account — and
each of them is a question somebody has to put to a running database. Putting a question to
a running database means speaking its protocol, and speaking its protocol is engine
knowledge. So either the core learns to speak one, or something else does the asking.

There is a third pull. Two or three of the ten look as though they need no engine at all:
the plan names the service unit, so a shared role could ask systemd about it; the plan
names the backup path and the service account, so a shared role could ask the kernel
whether one can write to the other. Apply is split exactly along that line — a `common`
role for accounts, directories and host settings, and an engine's role for everything
else — so the obvious thing is to split verify the same way.

## Decision

**An engine's role reads the instance and produces one observation document. The core reads
that document and judges it against the plan.**

The document is `schema/observation.schema.json`: a closed contract, an envelope naming the
plan and the host and the moment, and one entry per kind. Each kind's shape is fixed by
that schema, so a core that has never heard of an engine can read an answer the engine's
role produced. What the role does not put in it is anything only that engine understands —
it asks its own instance for values **in the plan's own spelling**, so that comparing the
two documents is a comparison rather than a translation.

`ansible/playbooks/verify.yml` reads the engine out of the plan, enters that role, writes
the document, and hands it to `basewright verify`. The split is the collecting playbook's,
line for line, and for the same reasons.

**The whole document comes from the engine's role, including the two or three parts a
shared role could have produced.** This is the part that was argued about, and the reason
is that apply's split earns its keep and this one would not. `common/layout.yml` creates an
account and four directories, and that is *identical work* whichever engine asked for it.
Asking whether a service is running is not identical work: for this engine it is one
systemd unit, for another it could be several, and a shared role deciding which would be a
shared role that knows one engine from another — the exact crack the architecture exists to
prevent. What the shared alternative buys is three tasks not repeated per engine; what it
costs is a second place to look for one document and a rule about which half owns which
kind. Three tasks is the cheaper thing to pay.

**Where engine knowledge has to be applied, it is applied by the role, before the document
is written.** A version string is reduced to its major part by the role, because which part
of a version string is the major one is engine knowledge. A parameter the server reports in
units of eight kilobytes is asked for in bytes by the role, because the plan records bytes.
An authentication method is marked as requiring a password or not by the role, because what
a method is called is the engine's vocabulary — while the method's *name* travels through
untranslated, so the report names the rule somebody has to go and delete.

**Two filters carry it across.** `basewright_observation` puts the envelope round what the
role read, so the contract has one implementation and pytest covers it rather than a
template assembling it field by field. `basewright_sockets` parses what `ss` printed, given
the process name the role supplies. Neither knows an engine; the role calling them does.

**One variable crosses back the other way, and it cannot carry the role's name.**
`basewright_observed` is the handover between an engine's role and a playbook shared by
every engine, so naming it `postgresql_observed` would mean `verify.yml` mentioning an
engine. It is the interface rather than a leak, which is why the linter's rule about it is
suppressed in that one place with the reason written beside it.

## Consequences

- A second engine writes a role that answers the same eleven questions, and writes no
  Python at all. If it cannot answer one of them, the check reports that nobody asked
  rather than that the instance fell short.
- The core's judgements are eleven functions over two mappings, and they are unit-tested
  without a database. Adding a kind is a change to the schema and to the registry beside
  it, reviewed together, and a test holds the two sides equal.
- `verify` reads two files and reaches nothing. Its tests need no network, no container and
  no server, which is the same property the rest of the deciding half has.
- The observation document is an artifact in its own right. It can be kept, attached to a
  change request beside the plan, and read again later — and the two together are the whole
  of what a verify report was derived from.

## Rejected alternatives

**The core connects to the instance.** The shortest path: a psql client library under
`basewright/`, and one process does everything. It puts an engine's name, its wire
protocol and its client library into the core, and it gives the deciding half a network
stack, connection handling and a credential to hold. ADR-0020 rejected this for `gather`
when the argument was weaker, because collecting facts at least has no protocol to learn.

**A shared role observes what the plan describes; the engine's role observes the rest.**
The apply split, applied here. Rejected above: it saves three tasks per engine and costs a
rule about which half owns which kind, in a place where the answer is not obvious — `paths`
is authoritative only from the instance, `log` is authoritative only from the filesystem,
and `port` could go either way.

**The role writes the document itself, as the collecting role does.** Symmetrical, and it
would have avoided the handover variable and its suppressed lint rule. It puts three tasks
— make the directory, render the contract, hand it to the CLI — into every engine's role,
where a second engine would eventually write them slightly differently. The contract is
written in one place instead.

**The role returns raw output and Python parses it.** How `gather` works, and it is right
there: parsing what a machine printed is exactly the kind of thing that has a wrong answer.
It does not transfer, because parsing *this* output means knowing which server printed it.
The role asks its instance for JSON instead, so what crosses the boundary is decoded rather
than parsed, and the one thing that genuinely is parsed — the socket table — has a parser
in the core that takes the process name as an argument.
