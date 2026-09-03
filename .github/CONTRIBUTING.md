# Contributing

Basewright has a narrow scope on purpose. The most useful contributions are profiles and
tuning rules, not new subsystems.

## Before you start

Check the scope. Creating infrastructure, scheduling backups, running a monitoring stack,
deploying application schemas, provisioning managed cloud databases, upgrading existing
instances across major versions and building a web UI are all permanently out of scope. If
something looks necessary and is not on the in-scope list, open a discussion rather than a
pull request — the scope list is the reason this tool stays finishable.

## The one rule

**Core logic never branches on an engine name.** Nothing under `basewright/` may mention a
database engine, in code, comments or docstrings. CI enforces this and the failure message
tells you what to do instead: if the core genuinely needs the information, extend the profile
JSON Schema so a profile can supply it, and send that schema change as its own commit.

The corollary is the shape of most contributions: an engine, an OS family or a tuning
decision is a change to `profiles/`, reviewable by a DBA rather than by a programmer.

## What a change has to ship with

Three rules, no exceptions, because these are the things that are easy to get subtly wrong
and hard to notice afterwards:

- **A sizing rule ships with a golden fixture.** The point is the diff: a change to a tuning
  rule has to appear in the pull request as a readable before/after of the rendered plan.
- **A gate ships with a unit test for both of its outcomes** — the pass and the failure.
- **An Ansible role ships with a molecule scenario.**
- **A change to something the documentation shows ships with the image regenerated.**
  `make assets` rewrites every diagram and terminal capture; `make assets-check` is what CI
  runs, and it fails on a single differing byte.

A sizing rule also ships with its `why`. A number without a reason is the situation this
project exists to end, and a rule whose explanation reads "sensible default" will be sent
back.

## Images

Every image under `docs/assets/` is produced by `tools/render_assets.py` and by nothing
else. Do not hand-edit an SVG and do not add a screenshot taken with a screenshot tool.

The rule exists for two reasons. A generated diagram cannot quietly stop matching the
architecture it illustrates, because the build regenerates it. And a terminal image is real:
captures are produced by running the command and keeping what it printed, which is also why
none of them can show a verb working before it works. A picture of behaviour that does not
exist is worse than no picture.

Adding one means adding a render function and an entry in `build()`. Output has to be
deterministic — no timestamps, no locale-dependent formatting — and comes in a light and a
dark variant, because half the people who open the page are reading it on the other one.

## Running the checks

```
make install
make all        # ruff, mypy, yamllint, pytest with coverage
make molecule   # role tests in containers; slow, run before you open the pull request
```

Everything CI runs is in the `Makefile`, so a green `make all` means a green pull request.

## Commits

Conventional Commits. The subject is imperative and under 72 characters; the body explains
the reasoning, not the diff — the diff is already in the commit. `git config commit.template
.gitmessage` sets up the template.

Commit messages, pull request descriptions, review comments and release notes carry no
attribution footers of any kind.

## Reporting a problem

Use the issue templates. For anything with a security dimension, follow
[SECURITY.md](SECURITY.md) instead of opening a public issue.

A refusal is not a bug. If preflight blocked a host, the report names the rule, the observed
value and the required value; the interesting question is whether the *rule* is right. If it
is not, that is a change to the rule in Git, where someone can review it — never a run-time
override flag, which is the one thing this project will not add.
