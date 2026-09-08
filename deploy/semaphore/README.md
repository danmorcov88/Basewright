# Semaphore setup

Semaphore is the operator interface and there is no other one
([ADR-0005](../../docs/adr/0005-semaphore-is-the-interface.md)). These five files are the
definitions it needs: one environment and four templates, matching the four verbs.

Nothing here is required to *use* Basewright — the playbooks run from any Ansible control
node, and the CLI reads documents anywhere. What this is for is the estate that runs
Semaphore already, so that provisioning a database is a form somebody fills in rather than a
command somebody remembers.

## What you need first

**A project.** Everything below hangs off one Semaphore project.

**A repository** pointing at this one, on the branch you deploy from. Semaphore clones it
per task, so the playbooks and the profiles arrive together — which is the point: a profile
is data, and it travels with the code that reads it.

**An inventory** holding the hosts you provision. Basewright starts at a reachable host
([ADR-0012](../../docs/adr/0012-starts-at-a-reachable-host.md)) and does not create one.

**A key** for the technical account
([ADR-0006](../../docs/adr/0006-dedicated-technical-account.md)). Not a personal key and not
a root password shared in chat: the account exists for Basewright, and its authorized keys
are managed outside this tool.

**Basewright installed on the Semaphore host**, because the playbooks call it:

```
pip install /path/to/basewright
```

**A durable directory for the plans**, and this one is worth a moment. A plan is produced by
one person and applied by another, sometimes days later, so the store has to outlive the
task that wrote it — a path inside the Semaphore container that is not on a volume will lose
every plan the next time the container is replaced, and the Apply template will refuse a
plan id that was real an hour ago.

```
install -d -m 0750 -o semaphore -g semaphore /opt/basewright/plans
```

## Loading the definitions

The ids in these files are zeros, because a project id, an inventory id, a repository id and
an environment id are facts about your installation rather than about Basewright. Fill them
in, then post them.

Load the environment first — the templates refer to it:

```
export SEMAPHORE=https://semaphore.example.internal
export TOKEN=...            # Semaphore: User settings -> API tokens
export PROJECT=1

jq --argjson p "$PROJECT" '.project_id = $p' deploy/semaphore/00-environment.json \
  | curl -sS -X POST "$SEMAPHORE/api/project/$PROJECT/environment" \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d @-
```

Then the four templates, with the ids that call came back with and the ids of the inventory,
repository and key you made above:

```
export INVENTORY=1 REPOSITORY=1 ENVIRONMENT=1

for f in deploy/semaphore/0[1-4]-*.json; do
  jq --argjson p "$PROJECT" --argjson i "$INVENTORY" \
     --argjson r "$REPOSITORY" --argjson e "$ENVIRONMENT" \
     '.project_id=$p | .inventory_id=$i | .repository_id=$r | .environment_id=$e' "$f" \
    | curl -sS -X POST "$SEMAPHORE/api/project/$PROJECT/templates" \
        -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d @-
done
```

They can equally be typed into the web interface. The files are the record of what the
survey fields are and what each one means; posting them is only the faster way to get there.

## The four templates, and the order they run in

| Template | Asks for | Changes the host |
| -------- | -------- | ---------------- |
| **Basewright: Preflight** | host, engine, version, instance | no |
| **Basewright: Plan** | the above, and the environment | no |
| **Basewright: Apply** | plan id, warnings acknowledged | **yes** |
| **Basewright: Verify** | host, instance | no |

**Apply asks for a plan id and not a host.** That is the shape of the whole tool: the plan
was built from one machine's facts and refuses to be applied to another, so the host is in
the artifact already. Asking for it again would be asking somebody to repeat something the
plan carries, and to be the one who gets it wrong.

**Verify asks for a host and an instance and not a plan id.** The store remembers which plan
each instance was applied from, so somebody asking whether a database is what it should be
does not have to know the id of a plan somebody else approved. That pointer is one line,
overwritten on every apply: it is not an audit trail, and an audit trail is a later phase.

**The plan id travels between the second and third rows**, and that is the separation §12 of
the brief calls a feature. The person who produces a plan and the person who applies it can
be different people, on different days, and what passes between them is an id that is also a
checksum: a plan edited after it was approved does not answer to the same name.

## What these templates do not carry

**Path overrides.** §12 lists them as a Plan survey variable and there is no field for them,
because there is nothing behind one: the layout comes from `layout.yml` in the profile, and
a path is a decision reviewed in a pull request rather than typed into a form by whoever
happens to be provisioning that afternoon. An estate that wants different paths changes one
file; an estate that wants them per host has a case to make, and it is not made here.

**A secret store binding.** Generated passwords are written through a sink chosen by a role
variable, and the implementation that ships is a file with mode 0600 on the control node.
Pointing that at Semaphore's own secret store is a variable and a small role, and it is not
written yet — so on a Semaphore installation the passwords land on the Semaphore host, which
is somewhere to know about rather than somewhere to leave them.

**Scheduling, RBAC and history.** Semaphore's, all three, which is the reason it is the
interface. Basewright does not reimplement any of them and would be worse at all of them.
