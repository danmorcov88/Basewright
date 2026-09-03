---
name: Engine or OS support
about: Ask for an engine, an engine version or an OS family to be supported
title: ''
labels: profile
assignees: ''
---

## What should be supported

Engine, versions, OS families and architectures.

## Why

Where it is in use, and what it would replace.

## What is known already

- Vendor repository, if there is one:
- Package and service names per OS family:
- Parameters that need sizing from host facts, and the reasoning for each:
- Minimum resources a production instance is allowed to run on:
- Post-install assertions that would prove the instance is sane:

## Note

Adding an engine is a change to `profiles/`, not to the core. If it turns out the core needs
to change, that is the interesting finding and it belongs in this issue.
