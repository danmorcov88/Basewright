# Security policy

## Reporting a vulnerability

Report privately through GitHub's [security advisory
form](https://github.com/danmorcov88/Basewright/security/advisories/new) rather than in a
public issue. Include what you did, what happened, and the version or commit.

You will get an acknowledgement within a few days. This is a personal project with no
support contract behind it; what it does offer is a fix or an honest explanation of why
there will not be one.

## What is in scope

Basewright provisions database instances and holds credentials in flight while it does so.
The reports that matter most are:

- **A secret reaching a place it must not be.** Generated passwords go to the secret store
  and nowhere else. If a password, key or token appears in a task log, a fact document, a
  plan, a rendered report or a config file with loose permissions, that is a bug of the
  first order.
- **A gate that can be bypassed.** A block is not overridable at run time, by design. A way
  to make `apply` proceed past a block, or to have a plan produced despite one, defeats the
  purpose of the tool.
- **An applied configuration that is insecure by default** — an authentication rule that
  trusts a non-local address, a data directory with permissions wider than the profile
  declares, an administrative account left with a default or empty password.
- **Privilege escalation on a target beyond what the declared operations require.**

## What is not in scope

- The security of the database engines themselves. Report those upstream.
- Anything reachable only by someone who already controls the machine running Basewright,
  or who already holds the technical account's credentials.
- A host that is refused. Refusal with a reason is the intended behaviour.

## How credentials are handled

Stated here so a reader can check the implementation against the intent:

- A dedicated technical account reaches targets. Not personal SSH keys, not a shared root
  password.
- Credentials never live in the inventory. They come from the secret store or from
  `ansible-vault` and are injected at run time.
- Generated passwords are written once, to the secret store. The plan records where the
  secret lives, never what it is.
- No password is accepted on a command line. A password in `argv` is visible to every
  process on the host and lands in shell history; it goes through an environment variable or
  standard input.
- The plan is designed to be safe to share, because it is the artifact people attach to
  change requests.
