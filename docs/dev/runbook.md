# Runbook

What to do when something goes wrong, written for whoever is looking at a red task and did
not write any of this.

The first thing worth knowing is that **a red task is usually the tool working.** Three of
the four templates change nothing, and their whole job is to refuse: a host that cannot
carry an instance, a plan that has been edited, an instance that no longer matches what it
promised. Those are answers. The report in the task log names the rule, what was found, what
was required, and what would have to change — read it before doing anything else, because it
is more specific than this page can be.

## The exit codes

| Code | What happened | What to do |
| ---- | ------------- | ---------- |
| `0` | The tool ran, and the answer is yes. | Go on to the next step. |
| `2` | The tool ran, and the answer is no. | Read the report. It names the rule and the way out. |
| `64` | The request itself is malformed. | Fix the command. Nothing was decided, so there is no report. |

The line between the two non-zero answers is where a document stopped being readable: **a
file that could not be read at all is `64`, and a file that was read and is not acceptable
is `2`.** A plan id the store has not got is `64`. A plan whose id no longer matches its
content is `2` — it is a plan, it is simply not the plan it claims to be.

---

## Preflight refuses a host

**This is the tool doing its job.** The report names every blocking rule, the value it
found, and the value it needed.

There is no override and there will not be one
([ADR-0004](../adr/0004-two-severities-no-override.md)). Two things can change: the machine,
or the request. If neither should — if the rule is wrong about a host that is genuinely
fit — then the rule is wrong, and it gets fixed in Git rather than skipped at the console.
That has happened twice, both times found by pointing the tool at a real machine, and both
fixes are in the status page under what a real host taught the rules.

**`repo.reachable` blocks and the host has a network.** The host was asked whether it could
reach the repository the profile names and reached nothing. Check the proxy, the firewall
and the DNS from the host itself, with the url printed in the report. A host that was never
asked reports the fact as absent and the rule skips — if it skipped, nobody named an engine.

**A sizing rule refuses because a fact was not reported.** Usually storage: two parameters
read whether the data path is rotational, and a rule that reads an unreported fact refuses
the plan rather than quietly omitting a parameter. What is left refusing after logical
volumes were handled is a host whose storage genuinely cannot be determined. The report says
which path.

## Preflight passes with warnings

Read them. They are acknowledged once, at apply, by the person who read them — that
acknowledgement is the record that somebody looked.

**Every plan carries the write-ahead log warning** unless the estate gave the log its own
mount. It is true, it is about the default rather than about the host, and it is discussed
in the status page under the seven values. If your estate does give it a mount, one line in
`layout.yml` changes and the warning stops.

## Plan produces nothing

A block ends it. There is no partial plan and no flag that produces one — the refusal is the
answer, and it is the same report preflight would have given.

## Apply refuses before touching anything

Four things have to be true, and the report says which one was not.

**"the plan has been edited."** The plan's id no longer matches a digest of its content.
Somebody changed the file after it was produced. Produce a fresh plan and have that one
approved; do not edit the id to match.

**"this host is no longer the machine the plan was built from."** The facts moved between
the plan and the apply. Identity — the operating system, the architecture, a filesystem's
type and whether it spins — must match exactly; capacity drifts only when it *shrinks*.
Produce a fresh plan against the host as it is now.

Two things the drift check cannot see, named in `UNCHECKED` in `basewright/drift.py`: an
engine somebody installed since the plan was made, and a port taken since. Both are found
later and less kindly — the packaging refuses, or the service fails to bind.

**"warnings nobody has acknowledged."** Somebody has to say they have read them. Read them,
then run Apply with the acknowledgement set.

**"no plan &lt;id&gt;."** The store has not got it. The message lists what the store does
hold, which usually settles it: either the id was mistyped, or the Plan task wrote into a
different store from the one Apply is reading. Check that both templates use the same
environment, and that the store is on a volume that outlives the task — a directory inside a
container that is replaced loses every plan in it.

## Apply fails partway through

Apply is not destructive: it creates and configures, and it does not drop data directories
or overwrite a configuration file without leaving a timestamped copy beside it. So the
normal answer is to fix what failed and run it again — the second run does the rest and
reports no change for what was already done.

**The package step fails.** Almost always the repository: the same thing `repo.reachable`
asks about, failing later because nobody ran preflight.

**The instance will not initialize.** The data directory has to be empty. If a previous
attempt left something in it, `initdb` refuses by name, and that refusal is worth reading
rather than working around — a directory with data in it is not one to clear on a hunch.

**The instance will not start.** Read the unit's journal and the cluster's own log. A clean
apply that will not start usually means the plan promised a configuration this host cannot
honour, which is a finding about the plan rather than about the machine.

## Verify fails

**The loudest thing this tool does, and the one that means the documentation is now wrong.**
The plan says the instance is one thing and the instance is another.

Each check reports one of three things.

**`FAIL`** — read back and it does not match. The report names what was found and what was
planned, and the remediation comes from the profile. The common one is a parameter changed
by hand: `ALTER SYSTEM` survives a reload and is read after every configuration file, so it
wins over the plan silently until this runs. Either put it back, or plan again and have the
new value approved — the point is that the artifact and the machine agree, not which of them
moves.

**`?` — could not be observed.** Nobody managed to ask. **This is not a pass and the run
does not verify the instance** ([ADR-0025](../adr/0025-a-check-nobody-could-run-is-not-a-pass.md)).
A cluster that is down produces one failure — the service — and seven of these; fix the one
and run it again.

**`UNPROVED` rather than `FAILED`** means nothing contradicted the plan and something could
not be asked. The instance may well be fine. This run did not establish it.

**"does not say which plan &lt;host&gt; is running."** The store has no pointer for that
host and instance. Either it was applied before the store existed, or through a different
store, or the instance name is spelled differently from the one the plan used. Verify with
the plan id directly to get past it, and check which store Apply is writing to.

---

## Where things are

| | |
| --- | --- |
| Facts collected from a host | `facts/<host>.json` on the control node |
| Plans | `<store>/plans/<plan_id>.json` |
| Which plan an instance runs | `<store>/instances/<host>/<instance>` |
| Observations verify judged | `observations/<host>.json` on the control node |
| Generated passwords | `~/.basewright/secrets/<location>` on the control node, mode 0600 |

The store's location is `basewright_plan_store`, set for all four templates in the Semaphore
environment. Under Semaphore it must be a volume: a path inside a container that gets
replaced loses every plan, and an id that was real an hour ago stops resolving.

`<location>` is what the plan's `secrets` section names. Which store wrote it is
`common_secret_store`: `file` holds the password itself, and `vault` — what the Semaphore
environment selects — holds an `ansible-vault` file, so reading one back takes the key:

```
ansible-vault view --vault-password-file ~/vault-password ~/.basewright/secrets/<location>
```

**"common_secret_store is vault and no vault password was given."** Apply refused before
generating anything, because `BASEWRIGHT_VAULT_PASSWORD` was not in the run's environment.
Under Semaphore it is a secret of type `env` on the Basewright environment; check the
template has that environment attached. Apply refuses rather than falling back, because a
password written without the key that was meant to protect it looks stored and is not.

## Running it without Semaphore

Everything above is a playbook, and the playbooks run from any control node.

```
ansible-playbook ansible/playbooks/preflight.yml -l db-01 -e basewright_engine_name=postgresql
ansible-playbook ansible/playbooks/plan.yml      -l db-01 -e basewright_engine_name=postgresql
ansible-playbook ansible/playbooks/apply.yml     -e basewright_plan_id=<id> -e basewright_accept_warnings=true
ansible-playbook ansible/playbooks/verify.yml    -l db-01 -e basewright_instance=main
```

Apply takes no `-l`: it reads the host out of the plan.

The CLI reads the documents those playbooks write, and reaches nothing itself. `basewright
plan --plan-id <id> --store <dir>` renders a stored plan for somebody to approve;
`basewright --help` lists the rest.

## What this tool will not do

Not gaps to be worked around — decisions, each with a record.

It does not create machines, networks or storage; it starts at a reachable host
([ADR-0012](../adr/0012-starts-at-a-reachable-host.md)). It does not schedule or verify
backups ([ADR-0013](../adr/0013-backups-are-out-of-scope.md)). It does not upgrade an
instance across a major version. It does not deploy application schemas. And it has no web
interface of its own and never will ([ADR-0005](../adr/0005-semaphore-is-the-interface.md)).
