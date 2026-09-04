# ADR-0022: The plan says how the instance is created, and that made it version two

**Status:** Accepted · 2026-09-04

## Context

The plan contract was frozen when the planner landed. Freezing it was the point: the plan
is the artifact a second person reviews, a change request carries, and `verify` reads back
off a disk months later, and none of that works if the shape of it drifts. Every change
from then on is a version of the contract rather than a patch, and this is the first one.

It was found by doing the thing the contract was written for. Before writing a line of the
apply role, `plan.json` was read against what that role would actually have to execute on a
Debian host: add the vendor repository, install the packages, make sure the service account
is there, create the directories, create the instance, write the configuration files, set
the host settings, enable and start the unit.

Eight steps, and the plan carries everything for seven of them. The repository with its
signing key, suite and components. The package names and the service unit. Every path with
its mode, its owner and the filesystem underneath it. The host settings, each with what it
was when the plan was made. The location of every secret. Every value the configuration
templates interpolate. All of it is there, and none of it has to be re-derived.

The fifth step is not there at all. `pg_createcluster` — and `initdb` under it, and the
equivalent for every other engine that installs a server without making an instance — is
told a locale, an encoding and whether to write page checksums. The locale lives in
`profile.yml` as `defaults.locale` and never reaches the plan. The encoding and the
checksum flag are nowhere: not in the plan, not in the profile, not anywhere a reviewer
could see them. And `changes`, the list somebody signs, says nothing about a cluster being
created.

None of it can be derived from what the plan does carry. The constraint is not incidental:
**apply consumes `plan.json` and nothing else**, and it exists so that the document somebody
approved is the document that runs. A role reaching into the profile for one value is a
role that could reach for a second, and a plan that no longer describes what will happen.

This was foreseen. ADR-0018 declared `changes` and `secrets` rather than inferring them,
and left an `initialization` section deliberately out on the grounds that its shape should
be decided by a real consumer rather than guessed at in advance. The consumer now exists.

## Decision

**`plan.json` gains an `initialization` section, and `schema_version` becomes `2`.**

A version rather than a patch, and it lands on its own — before the apply role rather than
inside the pull request that adds it. A frozen contract moving is the change most worth
reviewing by itself, and the goldens regenerate into a diff a person reads: the version, the
new section, one new line in `changes`, and a new name for every plan.

**The profile declares it, in `apply.yml`, and the core reads none of it.** A setting is a
name, a value and a `why`. The core carries all three into the plan and knows what none of
them mean; the engine's own role knows what each is a flag for. That is the only
arrangement under which the core can describe an act it does not understand, and it is the
same arrangement `tunables` already uses.

**The section is optional, and absent is a real answer.** An engine whose packages leave a
running instance behind them has nothing to create, and its plan carries no initialization
section rather than an empty one. A heading over nothing reads as something the plan failed
to say.

**The locale is not one of the settings.** It stays in `profile.yml`, where it already is,
and the planner copies it into the section. `locale.present` is a shared blocking rule that
reads `defaults.locale`, so the value in the plan is the value a host was proved to have. A
second spelling of it in `apply.yml` would be a second thing to keep in step, and the
failure that produces is an instance created with a locale nothing checked for — which is
exactly the failure `locale.present` exists to prevent, arriving through the back door.

**There is no `observed` beside a value, unlike a tunable.** Nothing exists yet to have
observed. That is the whole difference between the two, and it is why they are two things
rather than one with a field left empty.

**The change list spells the settings out rather than counting them.** A configuration file
is listed with a count of parameters, because nobody reviews twenty-three of them in a list
of changes. These are three or four, they cannot be changed afterwards, and they are
precisely what somebody approving a plan is reading that line to find out.

**Every setting's reasoning is rendered in full**, the way a sized parameter's is. This is
the one section describing something a second run cannot put right, which makes its
reasoning worth more than any other section's rather than less.

## Consequences

Apply can be written against the plan alone, which is the property the whole arrangement
rests on and the reason this had to be settled first.

Every plan produced before this is schema version one and does not carry the section. Apply
refuses a plan whose major version it does not implement rather than defaulting the fields
that moved, which is the behaviour the version field was put there for on the first day.
Nothing in this repository depends on an old plan: the goldens are regenerated, and a plan
in somebody's change request is a document to be reproduced rather than migrated.

Every golden plan has a new name, because the name is a digest of the content and the
content changed. That is the mechanism working: a plan that says something different is a
different plan, and it says so in its name.

Locale and encoding are now in the artifact somebody approves. They deserve to be there on
their own merits, independently of apply needing them — they are the two decisions on that
list that cannot be revisited without dumping and reloading every database in the instance,
and a plan that explains `shared_buffers` at length while saying nothing about the encoding
had its priorities the wrong way round.

The profile schema grows a section, so `writing-a-profile.md` grows one too. The cost of
declaring things rather than inferring them is that there is more to write down, and it is
the cost this project has already decided to pay everywhere else.

## Rejected alternatives

**Let the apply role read `defaults.locale` from the profile.** No contract change, one
value, and the role has to know which profile it is anyway. Rejected because it breaks the
one constraint apply has, and it breaks it for the cheapest imaginable reason — which is how
constraints get broken. The next value is easier to justify than this one was, and at the
end of that road the plan is a summary of what apply does rather than the definition of it.

**Put the locale, encoding and checksum flag in the plan as named fields of their own.**
Simpler to read, and no `settings` list to iterate. Rejected because it is the core learning
what an engine needs in order to be created: `encoding` and `data_checksums` are PostgreSQL
words, and a schema with fields named after them is a schema that has to grow a field the
day somebody writes a profile for an engine that wants a collation, a page size or a
character set. The name-value-reasoning shape carries all of them without the core knowing
any of them.

**Embed the whole thing as an opaque command line the role runs.** The profile writes
`initdb --data-checksums --locale={{ locale }}`, the plan carries the string, and the role
executes it. Maximally flexible and it needs no schema at all. Rejected twice over: it is a
plan carrying a shell command, which nobody can review as a set of decisions, and it is a
profile deciding rather than declaring — the thing ADR-0008 exists to prevent, in the file
where it would be least visible.

**Leave the section out and let apply default what it needs.** Every engine has a sensible
default encoding, and a role could apply one. Rejected because a default nobody stated is a
decision nobody made, and it would be made in the one place this project refuses to make
decisions. It also produces the specific failure the tool exists to end: an instance whose
encoding somebody has to log in and discover, six months later, with no artifact saying why
it is what it is.

**Version the section rather than the contract — add it as optional and leave
`schema_version` at one.** Nothing breaks, since old plans validate and new ones do too.
Rejected because it makes the version field decorative. Apply refuses a plan whose major
version it does not implement, and that promise is worth nothing if a plan of version one
might or might not carry the section apply is about to look for. A version that does not
move when the contract does is worse than no version at all.

## Related

- [ADR-0018](0018-what-apply-will-do-is-declared.md) — the decision this completes, and
  which left this section out on purpose until something consumed it.
- [ADR-0001](0001-plan-before-apply.md) — why the artifact has to describe the whole of
  what will happen.
- [ADR-0002](0002-engines-are-data.md) — why the settings are names the core does not read.
- [ADR-0008](0008-python-decides-ansible-acts.md) — why the profile declares choices rather
  than a command line that makes them.
- [ADR-0017](0017-a-plan-is-named-by-its-content.md) — why every plan in the repository has
  a new name after this.
