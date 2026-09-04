# ADR-0021: The collector is told what is being provisioned, for exactly one fact

**Status:** Accepted · 2026-09-04

## Context

Nineteen of the twenty shared gates read facts that are questions about a machine and
nothing else. How much memory it has, which filesystems it carries, what is listening on
5432, whether its clock is being kept right — a collector can answer all of them knowing
only that it has been pointed at a host.

`repo.reachable` is the twentieth, and it is not like the others. It asks whether the host
can reach the place its packages would come from. Where they would come from is written in
a profile, so the question cannot be put without naming one. A collector that wanted to
answer it on its own would have to either probe every repository every installed profile
declares — asking a host about repositories nobody is going to install from — or contain a
list of repositories of its own, which is engine knowledge in the shared half and the one
thing the architecture does not permit (ADR-0002).

This is the chicken and the egg that has kept the rule skipping since it was written. The
gate has been complete, with both of its outcomes tested, since session 5; the fact it
reads has been in the contract for just as long; and every host collected so far has left
it absent, so the rule has reported "nobody asked" on every run.

There is a further wrinkle that makes the shape of the answer matter. `reachable_
repositories` is the one three-valued fact in the contract. Absent means the question was
never put. Present and empty means the host was asked and reached nothing, which is a
refusal. Present with urls means the host proved it can reach them. Collapsing the first
two — writing an empty list whenever nobody asked — would turn every ordinary collection
into a blocked host, which is the worst available failure: a refusal that is nothing to do
with the machine.

## Decision

**The collecting playbook takes one optional input naming what is being provisioned, and
uses it for one fact.**

`gather_engine` looks a profile up under `profiles/`, and `gather_profile` reads a
directory, exactly as `--engine` and `--profile` do on the command line. Neither is
required. Without one, the question is not put, the fact is absent, and the rule reports
that nobody asked.

**Which urls to probe is decided in Python, from the profile.** `urls_for` in
`basewright/facts/repositories.py` reads the repository the profile declares for this
host's operating system family and fills in what the profile leaves open. The role reaches
it through a filter that is a two-line bridge, the same arrangement the document itself
uses (ADR-0020). The role never sees a repository it did not get from a profile, and there
is no engine name anywhere in it.

**The url is probed exactly as the profile spells it.** The rule compares urls for
equality, so a probe of a url that differs by a trailing slash proves something about a
repository nobody will install from. Substitution goes through the same `substitute` the
planner uses, against a deliberately narrower vocabulary: everything a host reports plus
the profile's own defaults, and nothing a request settles. A repository url that reached
for the environment being provisioned would be one string while it was probed and another
while it was installed from, and the fact would be compared against a url nobody tried.

**Only the repository is probed, never the signing key.** The key has a url too. No rule
reads it, and a fact no rule consults is a fact that rots quietly, because nothing fails
when it stops being collected correctly.

**Any HTTP status counts as reached.** A status — 200, 403, 404 — proves the host resolved
the name, opened a connection, completed the TLS handshake and was answered. That is the
whole of what the rule asks. Deciding which statuses mean a *working* repository would
mean knowing how each family lays its repositories out, which is engine knowledge again.

**A probe never fails the run.** Not reaching a repository is the outcome a blocking rule
exists to receive. A task that failed on it would end the run before the document carrying
that outcome had been written, which is the one result nobody could act on.

## Consequences

`repo.reachable` reports a verdict. That is the last piece of A1, and the fact that has
been named in every status page since session 5 as the one thing still missing.

The collecting role now has an input that is not about the host. That is a real cost and
it is the reason this is a decision rather than a patch: everything else the role does is
true of any machine whatever is going to be installed on it, and this one thing is not.
It is contained to a single optional variable, a single filter and a single fact, and the
role remains read-only and remains free of engine names — the guard in
`test_engine_names_absent_from_core.py` scans it exactly as before.

Facts collected before a profile was chosen do not carry the answer, and cannot be made to.
A document collected in the abstract and used later against three candidate engines is
still a perfectly good document; it will skip this one rule and say so. That is the right
behaviour and it is why absent had to stay distinguishable from empty.

The probe is one request per repository, from the target, on a short timeout. It is the
only outbound request the collecting step makes, and it is made to the same host the
package manager would talk to a few minutes later during apply.

A repository behind a proxy that answers on the repository's behalf will be reported as
reached. This is accepted: so will `apt`, for the same reason and at the same moment.

## Rejected alternatives

**Leave the rule skipping, and let apply discover it.** The status quo, and it has an
argument: apply will find out within seconds of starting, and its failure names the
repository. Rejected because a preflight that cannot answer the question it was written to
answer is a preflight that lets a host through to the step that changes it. The whole
thesis is that refusal happens before anything is touched, and "the first task of apply is
where this would otherwise be discovered" was always a description of the gap rather than a
defence of it.

**Probe every repository every installed profile declares.** Keeps the collector ignorant
of what is being provisioned, and the collected document then answers the question for any
engine. Rejected because it asks a production host to make outbound requests to vendors
nobody has any intention of installing from, which is a thing an operator would rightly
object to, and because it grows linearly with the profiles installed while answering one
question.

**Put the repository urls in the inventory, or in a variable an operator sets.** No profile
reading in the role at all. Rejected because it is the same knowledge in a second place,
maintained by hand, and diverging from the profile silently. The failure it produces is a
host that proved it can reach a url the plan will not use.

**Have the CLI collect this one fact from the control node.** The control node already
loads the profile, so it could probe the repository itself and merge the answer in.
Rejected because it answers the wrong question. Whether the control node can reach a
repository says nothing about whether the target can, and those two machines are routinely
on different networks — which is precisely the situation the gate exists to catch.

**Write an empty list whenever nobody asked, and drop the three-valued fact.** Simpler
contract, simpler collector, one less thing to explain. Rejected because it makes every
ordinary collection produce a blocked host for a reason that has nothing to do with the
host. Absent and empty are different answers and the rule was written to tell them apart.

## Related

- [ADR-0020](0020-the-playbook-is-the-entry-point.md) — the collecting arrangement this
  extends, and the bridge pattern it reuses.
- [ADR-0002](0002-engines-are-data.md) — why the urls come from a profile rather than from
  the role.
- [ADR-0004](0004-two-severities-no-override.md) — why a host that cannot reach its
  repository is refused rather than warned.
- [ADR-0011](0011-native-packages-from-vendors.md) — why there is a vendor repository to
  reach in the first place.
