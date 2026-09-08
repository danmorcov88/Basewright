# ADR-0027: The second secret store is ansible-vault, not Semaphore's

**Status:** Accepted · 2026-09-08

## Context

§11 of the brief is a list of constraints rather than suggestions, and one of them is this:
*"Credentials never live in the inventory. They come from Semaphore's secret store or
`ansible-vault`, injected at run time."* Another is that *"generated passwords are written
once, to the secret store, and never to a log, a fact, or the plan."*

Until now there was one implementation, and it was a file with mode 0600 on the control
node. On any machine that is the whole of the protection; under Semaphore it means the
generated passwords sit on the Semaphore host, next to the tool, rather than inside the
store the tool already has. It was named as the largest thing left undone rather than left
to be discovered, and it was named first.

The sink was described as a seam, and it was closer to a variable: `common_secret_store`
chose between the members of a list with one member in it, and the tasks were written
inline in the file every caller goes through. A second implementation would have meant
editing that file, which is the opposite of what a seam is for.

So there were two questions. Whether the sink dispatches — which is a straightforward yes,
and is the smaller half. And which of the two things §11 names is the second
implementation, which is not obvious at all, because the two are not equivalent.

## Decision

**The second store is `ansible-vault`. `file` stays the role's default, and
`deploy/semaphore/00-environment.json` selects `vault` for a Semaphore installation.**

`ansible/roles/common/tasks/secret.yml` now dispatches and implements nothing:
`secret_file.yml` and `secret_vault.yml` sit beside it, and a third is a file and a name in
`common_secret_stores`. Both keep the same two-part promise — `common_secret_value` is what
the store holds, `common_secret_is_new` says whether this run generated it — so no engine
role learns which one answered.

The vault store keeps an ordinary `$ANSIBLE_VAULT` file where the plaintext one went,
encrypted under a password taken from the run's environment. Under Semaphore that password
is an environment secret of type `env`, which is exactly §11's "injected at run time"; the
key lives in Semaphore's store and what it protects lives beside the run, and the two are
never in the same place.

**Semaphore's own store was rejected on a fact about its API rather than on convenience.**
It is write-only, by design and correctly: `EnvironmentSecretRequest` carries a `secret`
field on POST and PUT, and the `EnvironmentSecret` returned by GET carries `id`, `name` and
`type` and no value at all. Changing one is a delete followed by a create.

That is disqualifying here, because the store's contract is to hand back what it holds. A
second apply of the same plan must return the password the first apply generated; a store
that cannot be read would have to roll a new one, which locks out whoever was given the
first, and nothing says so until somebody tries to connect. The alternative — writing to
Semaphore *and* keeping a local copy to read back — is the problem restated with an extra
network call in it.

Three smaller reasons point the same way, and none of them would have been sufficient
alone: writing to that API needs a token that is itself a secret, on the one path in this
project that exists so a secret does not have to be handled; it needs the control node to
reach Semaphore, which nothing else here does; and it cannot be put under a molecule
scenario without standing up a Semaphore, so it would have shipped unproven. The project's
rule is that a role arrives with a scenario, and a store that cannot be exercised on a
container is a claim rather than a feature.

## Consequences

- **A copy of the control node's disk is no longer a copy of every password Basewright has
  generated**, on any installation that selects the vault store. That is the whole of what
  this buys and it is worth stating plainly, because it is smaller than "the passwords are
  in Semaphore's store" and larger than nothing.
- **Retrieving a password is `ansible-vault view --vault-password-file` against the file.**
  Not a web interface. This is the cost of the choice and it is deliberate: the tool that
  opens the file is one every Ansible estate already has, which is most of the reason for
  preferring an ordinary vault file over anything this project could have invented.
- **A vault store with no key refuses.** It does not fall back to writing plaintext, and it
  refuses before generating anything. A password written without the key that was supposed
  to protect it is worse than the default store, because the default does not claim to be
  protecting anything.
- **`file` remains the default**, so an existing control node keeps finding the passwords it
  already generated, and a scenario or a bare Ansible run needs no key management to work.
  The Semaphore environment file is where the other choice is made, because that file exists
  to say what a Semaphore installation needs.
- **What this does not solve is one vault password per installation.** There is no rotation,
  no per-instance key and no key distribution; those are somebody's key management and this
  project does not have an opinion about whose.

## Rejected alternatives

**Write to Semaphore's secret store over its API.** The real target, and it cannot keep the
contract: the API returns no secret values, so the store could not hand back what it holds.
Argued above.

**Ship nothing and keep naming the gap.** Defensible — a named gap is better than an
unproven fix — and it is what the previous session did. It stops being the better answer
once there is an implementation that is local, testable on a container, named in the same
sentence of the brief, and honest about being smaller than the thing it substitutes for.

**Encrypt with something of this project's own.** A few lines of Python and a filter, and
then a password that only Basewright can open. Rejected on the grounds that made the vault
format attractive: the value of an ordinary vault file is that recovering a password does
not depend on this repository still existing.

**Make `vault` the default.** Rejected because a changed default moves where an existing
installation looks for passwords it has already issued, and because it would make every
plain Ansible control node refuse until somebody set a key. The Semaphore environment gets
the safer choice; the role keeps the working one.
