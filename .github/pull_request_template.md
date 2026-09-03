## What this changes

<!-- The change and, more importantly, the reasoning behind it. -->

## Why

<!-- What was wrong, or what became possible. Link the issue if there is one. -->

## Checklist

- [ ] Nothing under `basewright/` mentions a database engine by name.
- [ ] A sizing rule, if added or changed, ships with a golden fixture and the plan diff is
      visible in this pull request.
- [ ] A gate, if added or changed, has a unit test for both of its outcomes.
- [ ] An Ansible role, if added or changed, has a molecule scenario.
- [ ] A `why` is present on every new rule, and it explains the number rather than restating it.
- [ ] No secret is written to a log, a fact document, a plan or a report.
- [ ] The change is within the project's stated scope.
- [ ] `make all` passes locally.
