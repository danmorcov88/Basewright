# ADR-0005: Semaphore is the interface; there is no custom web UI

**Status:** Accepted · 2026-09-03

## Context

The five verbs need to be runnable by people who are not going to use a terminal for it, and
runnable in a way that leaves a record. That implies a surface with a form to fill in, a
place to keep credentials, some notion of who is allowed to run what, and a history of what
was run and what it printed.

Written down as a list, those requirements look like a small web application. They are not.
Authentication, role-based access control, a secret store that is safe at rest, task
scheduling, log capture, log retention, and the ongoing security maintenance of all of it
add up to more code and more risk than the tool this project is actually about.

Ansible Semaphore is already deployed in the environment this is built for, and already
provides every one of those things. Building a second one alongside it would mean
maintaining two access-control models, two secret stores, and two audit trails that disagree
in the interesting cases.

There is also a failure pattern worth naming. Internal tools that grow a UI tend to stop
being the tool and start being the UI: effort moves to the interface, the interface acquires
opinions, and the substance — here, the gate rules and the sizing decisions — stops
improving. This project's substance is exactly the part with no visual interest.

## Decision

Ansible Semaphore is the operator interface. Basewright ships template definitions for it
and does not ship a user interface of its own — not a web application, not a TUI, not an API
server. This is permanent, not a phase.

Four templates, matching the four verbs an operator invokes:

| Template                | Survey variables                                   |
| ----------------------- | -------------------------------------------------- |
| `Basewright: Preflight` | host, engine, version (optional), instance name    |
| `Basewright: Plan`      | the above, plus environment and path overrides     |
| `Basewright: Apply`     | plan id, accept-warnings                           |
| `Basewright: Verify`    | host, instance name                                |

`deploy/semaphore/` holds the definitions as JSON plus a setup guide, so the interface is
version-controlled and reproducible rather than clicked together once and forgotten.

Semaphore supplies what it is good at: the survey form, RBAC, the secret store credentials
are injected from ([ADR-0007](0007-secrets-never-in-artifacts.md)), scheduling, task history
and logs. Basewright supplies the console renderings, which are designed to be read in a
task log rather than in a terminal that supports colour and cursor movement.

`Apply` takes a plan id rather than a host and an engine. Plans are written somewhere
durable, so the person who applies a plan can be a different person from the one who produced
it — a separation this ADR is partly in service of.

## Consequences

The project stays the size of its actual problem. No session handling, no password reset
flow, no front-end dependencies, no CVE feed for a JavaScript bundle, and no second place
where permissions are defined.

Operator-facing changes are cheap: a new survey variable is a small JSON change, reviewed
like anything else.

Rendering has a constraint worth stating. The console output is the interface, so it has to
be legible as plain text in a log viewer — no colour that carries meaning, no box-drawing
that assumes a width, no progress animation. That has been a good constraint: it is the same
requirement that makes the plan readable in a pull request.

The costs are real. Basewright inherits Semaphore's limitations, including the shape of its
survey inputs, and cannot offer an experience Semaphore cannot express — a plan diff rendered
side by side, for instance, will be text. An environment that does not run Semaphore has the
CLI and its own scheduler, which is a less finished experience. And Semaphore becomes an
operational dependency: its availability and its upgrade cycle are now this tool's concern.

Those are accepted. The alternative is not "a better interface"; it is a worse database
provisioner with an interface attached.

## Rejected alternatives

**A small custom web UI.** Full control over the experience, no dependency on Semaphore's
survey model. Rejected because the interesting parts of a provisioning UI are the parts
Semaphore already solved — auth, RBAC, secrets, history — and reimplementing them badly is
the most likely outcome. The plan artifact is what makes this tool reviewable, and it is
reviewable in a text editor.

**An HTTP API with a thin front end.** More modular, and it would let other systems drive
Basewright. Rejected for now on scope grounds rather than principle: it is a second interface
to secure and authorise, and nothing in the roadmap needs programmatic invocation that the
CLI and Semaphore's own API do not already cover. If that changes, it is a new decision, and
this one gets superseded rather than quietly stretched.

**AWX or Ansible Automation Platform.** Strictly more capable. Rejected because it is
substantially heavier to run than what the environment already has, and the capabilities it
adds beyond Semaphore are ones this tool does not use. The template definitions are simple
enough that porting them later is not a large piece of work.

**Terminal UI in the CLI.** Cheap, no server, pleasant for the person at the keyboard.
Rejected as the primary interface because it leaves no record and no access control — the
two things this decision is actually about.

## Related

- [ADR-0001](0001-plan-before-apply.md) — why `Apply` takes a plan id.
- [ADR-0004](0004-two-severities-no-override.md) — the warning acknowledgement is a survey
  variable, and the acknowledgement lands in the task history.
- [ADR-0007](0007-secrets-never-in-artifacts.md) — Semaphore's secret store is where
  credentials come from.
