# ADR-0026: The profile's seven values are decisions, not placeholders

**Status:** Accepted · 2026-09-08

## Context

§21 of the brief names seven pieces of information that "cannot be invented and must come
from the team": path conventions, the service account, locale and encoding, authentication
rules, minimum resources, OS families, and the port convention. It also says what to do
until they arrive — ship reasonable upstream defaults, keep them in `profiles/`, and mark
them in the status page as placeholders.

That is what has been done since the first profile shipped, and the status page has carried
a seven-row table saying **every row is an assumption, not a policy**.

Two things make that position no longer the right one.

**Phase A is finished and §21 said it could not be.** The brief's own sentence is
"implementation can begin without them; Phase A cannot finish without them." Phase A has
finished — a bare container is read, gated, planned for, provisioned and verified, in CI,
on every pull request. Something has to give: either Phase A is not finished, which is not
true, or the sentence was about a risk that turned out to be smaller than it looked.

It was the second. Six of the seven values turned out to be forced rather than chosen. The
paths are where the vendor's packaging puts things; moving them breaks `pg_lsclusters` and
the packaged logrotate for no gain. The service account is the one the package creates, and
creating it first would take a different uid from the one the package's files are owned by.
The encoding is the only defensible answer in 2026. The authentication rules are the
narrowest set that leaves a usable instance. The OS families are the ones that are tested,
and no others. The port is the registered one. None of those is waiting for anybody.

**A value marked "assumption" is a value nobody argues with.** This is the more important
half. A row that says it is provisional reads as a row that will be dealt with later, and
"later" for a placeholder that already works is never. A reviewer skips it. The estate that
deploys this never notices it had an opinion to give, because the page told them the
question was still open somewhere else.

## Decision

**The seven values are the project's decisions. The status page states them as decisions,
with the argument for each and the one line that changes each, and no longer describes them
as placeholders.**

The values themselves do not change. They were reasonable when they were chosen as
defaults and nothing has been learned since that argues against any of them; what changes
is that the repository now owns them rather than holding them in trust.

**Two of the seven are named as the ones an estate is most likely to change**, because
saying "these are decisions" without saying which ones are contentious is the same evasion
in a different direction:

*The backup path.* `/backup/postgresql/<instance>` with a 50 GB floor, and a host without
such a mount is refused. `/var/backups` was rejected because it is a few kilobytes of dpkg
state on the root filesystem of every machine, so the floor there would refuse almost every
host for the wrong reason. What an estate calls the mount is the open half; that it is a
mount somebody provisioned on purpose is the assertion, and it is the assertion worth
keeping.

*The write-ahead log.* It defaults to the upstream location inside the data directory, so
on any host without a path override the profile warns that the two share a mount. **That
warning fires on every plan**, which is the strongest argument against it: a warning that
is always true is a warning nobody reads, and ADR-0004 is built on warnings being read. It
stays anyway, and the reason is that the alternative is worse. Giving the log its own mount
by default would make every host without one *refuse* rather than warn, which is a blocking
rule inherited by an estate that never asked for it. A warning acknowledged once per plan
is the smaller cost, and the acknowledgement is the record that somebody looked.

**Anything an estate does change is a line in a YAML file in `profiles/`, not a fork.**
That is what makes owning these values cheap rather than presumptuous: the whole point of
engines being data (ADR-0002) is that a value somebody disagrees with is a value they can
edit in a pull request against their own copy of the profile, with the argument for the
original still written beside it.

## Consequences

- §21 is closed. The status page has a table of decisions rather than a table of debts, and
  the README's project status stops saying Phase A is blocked on information.
- A profile author reading the table learns what to change and where, rather than learning
  that the question is open. That is the more useful of the two things a table can say.
- The minimum resources stay blocking with no run-time override (ADR-0004). They were the
  row most in need of somebody willing to defend them, and this is that.
- If the estate does supply different numbers, nothing here resists it: seven values, seven
  lines, one pull request. What is no longer true is that the repository is waiting.

## Rejected alternatives

**Keep them marked as placeholders until somebody answers.** The honest-looking option, and
the one this repository has taken for four sessions. It stops being honest once Phase A is
finished and the placeholders are what shipped: a value that has been in production
behaviour through an entire phase is a decision whether or not the page admits it.

**Ask for the seven answers again and block Phase B on them.** Blocks a finishable project
on an input that has not arrived in four sessions, to change values that six times out of
seven are forced anyway. The one place it would genuinely help — the backup mount's name —
is one line, and is named above as the line to change.

**Weaken the minimums so fewer hosts are refused.** Tempting, because a floor that refuses a
host is the most visible thing on the list. Rejected for the reason the floors exist: they
are there to catch a request pointed at a machine nobody meant to provision, and a floor low
enough never to fire is not a floor.
