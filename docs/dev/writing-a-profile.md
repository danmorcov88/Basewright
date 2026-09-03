# Writing a profile

A profile is how Basewright learns an engine. It is seven YAML files and a directory of
templates, and it is the only place in the repository where knowledge of a particular
database lives. Nothing under `basewright/` knows the name of any engine, and nothing in
a profile is code — which is the point: a profile is reviewable by whoever knows the
database, rather than by whoever knows Python.

Adding an engine means adding a directory. If it ever seems to also mean editing the
core, that is a finding: the missing information belongs in the schema, and the schema
gets extended so the profile can supply it.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/profile-anatomy-dark.svg">
  <img alt="The seven files of a profile, what each declares, and which step reads it"
       src="../assets/profile-anatomy-light.svg" width="900">
</picture>

## Where things live

```
profiles/<engine>/
├── profile.yml           # identity, OS families, defaults
├── support-matrix.yml    # engine version x OS x arch x end of life
├── requirements.yml      # gate rules this engine adds, and the way out of each
├── layout.yml            # paths, modes, the service account
├── sizing.yml            # parameter rules, each with its reason
├── packages.yml          # repositories, packages, service unit, per OS family
├── verify.yml            # assertions about the running instance
└── templates/            # configuration templates
```

Each file has a JSON Schema in [`schema/`](../../schema), and every object in every schema
is closed: an unknown key is an error rather than something quietly ignored. That is not
pedantry. A profile that can carry a key the core does not read is a profile that can
imply behaviour the core does not have, and the first person to find out is whoever runs
it against a production host.

## Checking your work

```
python -m basewright.profiles profiles/<engine>
```

This is not one of the four verbs — those act on a host, and this acts on the repository.
It reads the profile, validates each file against its schema, and then checks the
agreements *between* files that no single schema can see: that every file names the same
engine, that the default version is one of the versions listed, that every operating
system family used is declared and can actually be installed on, and that no identifier is
used twice.

Everything wrong is reported at once, with the file, the place inside it, and what to do
about it:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/profile-refused-dark.svg">
  <img alt="The loader refusing a profile, naming each defect and its remedy"
       src="../assets/profile-refused-light.svg" width="800">
</picture>

The remedy in each of those messages is the schema's own description of the field. There
is one place to write down what a field is for, and both the schema and the refusal read
from it.

`make schema` runs the same check over every profile in the repository, and so does CI on
every pull request.

## The seven files

### `profile.yml` — identity

```yaml
---
engine: exampledb
display_name: ExampleDB
profile_version: "1.0.0"
summary: A fictional engine used to exercise the profile schema and the loader.
os_families:
  - debian
  - rhel
defaults:
  port: 6432
  instance: main
```

`os_families` is the single list of families the profile supports; the support matrix and
the package definitions are checked against it. `profile_version` is the version of the
profile, not of the engine, and it is carried into `plan.json` so that a value in an old
plan can be traced back to the rule that produced it.

### `support-matrix.yml` — what may be installed where

Basewright never chooses a version. A human does, and this file is what that choice is
validated against.

```yaml
---
engine: exampledb
default_version: "3"
versions:
  - version: "3"
    eol: "2029-05-01"
    arch: [x86_64, aarch64]
    supported_os:
      - family: debian
        distro: ubuntu
        versions: ["22.04", "24.04"]
```

A version approaching its end of life produces a warning rather than a refusal: the
operator is told, and decides. `status: allowed_with_warning` marks a version that is
still maintained upstream but is not what a new instance should be built on.

### `requirements.yml` — the gates this engine adds

The shared gates apply to every engine. This file is what one engine adds to them.

```yaml
---
engine: exampledb
rules:
  - id: exampledb.mem.min_total
    severity: block
    title: Enough memory to run an instance at all
    expr: host.memory.total_bytes >= 2 * GiB
    remediation: >-
      Give the host at least 2 GiB of memory, or provision this instance somewhere else.
```

There are two severities and there is no third. There is no flag that turns a block into a
warning: if a block is wrong, the rule is wrong, and the rule is fixed in Git where a
reviewer can see it. A rule ships with a test for both of its outcomes.

`remediation` is not optional and is not decoration. "Refused because /backup has 12 GiB
free and this profile requires 100 GiB" is a useful answer; "preflight failed" is not.

### `layout.yml` — where the files go

```yaml
---
engine: exampledb
paths:
  data:
    default: /var/lib/basewright/{{ engine }}/{{ instance }}/data
    mode: "0700"
    min_free: 20GB
service_account:
  name: exampledb
  create_if_missing: true
  shell: /usr/sbin/nologin
```

Which purposes a profile defines is the engine's business; `data` and `log` are the two
every engine has. Each `min_free` becomes a block threshold, so it has to be a number
someone will defend in a review.

### `sizing.yml` — the parameters, and why

```yaml
---
engine: exampledb
rules:
  - id: exampledb.cache_size
    parameter: cache_size
    expr: 0.25 * host.memory.total_bytes
    unit: bytes
    min: 128MB
    max: 8GB
    why: >-
      A quarter of memory is the standard starting point for a shared cache, and it is
      capped because past that point the operating system page cache is the better place
      for the memory.
```

`why` is rendered into the plan next to the computed value. A number without a reason is
the situation this project exists to end, so the schema requires it.

The arithmetic is data here and is evaluated in Python, where it can be unit-tested
against fixture hosts — a machine with 2 GiB, one with 512 GiB, one with rotational disks.
A sizing rule ships with a golden fixture, so a change to it shows up as a readable diff in
the pull request rather than as a number that quietly moved.

### `packages.yml` — what to install, from where

```yaml
---
engine: exampledb
families:
  debian:
    repository:
      name: exampledb
      url: https://packages.example.invalid/apt
      key_url: https://packages.example.invalid/apt/signing.asc
      suite: "{{ os.codename }}"
      components: [main]
    packages:
      - exampledb-server-{{ version }}
    service: exampledb@{{ version }}-{{ instance }}
```

Native packages from vendor repositories. No compiling from source, no unpacking a tarball
into `/opt`. Plain HTTP is not accepted for a repository URL: a package repository reached
without transport security is a supply chain nobody controls.

Every family declared in `profile.yml` needs an entry here. A profile that claims a family
it cannot install on refuses at apply time, which is the latest possible moment to find
out.

### `verify.yml` — proving the instance matches its plan

```yaml
---
engine: exampledb
checks:
  - id: exampledb.auth.no_trust
    kind: auth
    title: No password-free rule is reachable from a non-local address
    remediation: >-
      Remove the rule. An instance that trusts the network is not fit for production.
```

Apply promises something; these are what proves it. A verify failure is loud, because it
means the instance is no longer what the documentation claims it is.

This is the least settled of the seven files. Its consumer is the verify step, which is
built in Phase A, and the schema is expected to gain detail there.

## Conventions worth knowing

- **Identifiers are namespaced and unique.** `exampledb.cache_size`, not `cache_size`. An
  identifier names one rule for the life of the profile: it is what a refusal prints and
  what someone searches for six months later.
- **Quote versions and modes.** `"16"` and `"0700"`, so that YAML does not helpfully turn
  them into the number sixteen and the number four hundred and forty-eight.
- **Sizes carry their unit.** `8GB`, `128MB`, `2GiB`. Decimal and binary units are both
  accepted and mean what they say.
- **Placeholders** are `{{ engine }}`, `{{ instance }}` and `{{ version }}`. They are
  resolved when the plan is assembled, not when the profile is read.
- **No secret ever appears in a profile.** Generated credentials go to the secret store,
  and the plan names the location, never the value.

## Adding an engine

1. Copy the shape of an existing profile and change the identity.
2. Fill in the support matrix from what the vendor actually publishes packages for.
3. Write the sizing rules with their reasoning. This is the part worth taking time over.
4. Run `python -m basewright.profiles profiles/<engine>` until it is quiet.
5. Add the golden fixtures for the sizing rules, and a molecule scenario for the apply
   role.

If any of that required a change under `basewright/`, say so in the pull request rather
than working around it. That is the finding the second engine exists to produce.
