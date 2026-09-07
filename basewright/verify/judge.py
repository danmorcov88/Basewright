"""What each kind of check means, and how one is decided.

A profile declares checks; each names a ``kind``; the kinds are a closed enumeration in
``schema/verify.schema.json``. This module is the other half of that enumeration: one
judgement per kind, and the registry below is the whole of what the core can be asked to
decide. A profile cannot introduce a kind, because a kind is a question the core knows how
to put to an observation and an answer somebody wrote a judgement for.

Nothing here knows an engine. Every judgement reads two things -- what the plan promised
and what the observation recorded -- and both arrive as plain documents. Where a comparison
needs engine knowledge, that knowledge has already been applied by the role that took the
reading: a version string is reduced to its major part by the role, a method that requires
no password is marked as such by the role, and a server that reports a byte count in pages
is asked in bytes by the role. What is left here is comparison, which is why it can be
written once for every engine there will ever be.

Three outcomes, and the third carries most of the design. A kind the observation does not
carry is ``unobserved``: the run failed to ask, which is not the instance failing to
comply, and it is not a pass either (ADR-0025). A kind whose *plan* side is missing is
also ``unobserved``, and for a stronger reason -- a profile asking to verify a promise the
plan does not make is a defect in the profile, and the loudest place to find it is the
report rather than a traceback.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from basewright.verify.model import Outcome

#: How a check reports back before its remediation and title are attached: what happened,
#: what was read, and what was promised.
Finding = tuple[Outcome, str, str]

#: Addresses an instance can be reached at only from the machine it runs on. Used by the
#: derived ``loopback_only`` a profile's expression reads, and by nothing that judges: what
#: counts as too wide is a profile's decision, and this is only what counts as local.
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def passed(observed: str, expected: str = "") -> Finding:
    """The instance is what the plan said."""
    return (Outcome.PASS, observed, expected)


def failed(observed: str, expected: str = "") -> Finding:
    """The instance is not what the plan said, and here is the difference."""
    return (Outcome.FAIL, observed, expected)


def unobserved(reason: str) -> Finding:
    """Nobody managed to ask. Not a pass, and reported as its own outcome."""
    return (Outcome.UNOBSERVED, reason, "")


# ------------------------------------------------------------------------ the judgements


def judge_service(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """The unit the plan named is enabled and active.

    Enabled matters as much as active, and it is the half that gets forgotten: an instance
    that is running and not enabled is one that disappears at the next reboot, and the
    reboot is usually months later and somebody else's morning.
    """
    planned = _dig(plan, "packages", "service")
    if planned is None:
        return unobserved("the plan names no service unit for this instance")

    unit = reading["unit"]
    state = "active" if reading["active"] else "not active"
    boot = "enabled" if reading["enabled"] else "NOT enabled at boot"
    observed = f"{unit} is {state}, {boot}"

    if unit != planned:
        return failed(observed, f"{planned} is enabled and active")
    if reading["active"] and reading["enabled"]:
        return passed(observed, f"{planned} is enabled and active")
    return failed(observed, f"{planned} is enabled and active")


def judge_port(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """The instance is on the planned port, and on no other port.

    The port is what the plan carries, so the port is what this judges. An instance bound
    more widely than the estate intends is a real finding and a profile says so with an
    expression over ``observed.port``, because which addresses are acceptable is a decision
    that belongs in the file where somebody would go to argue with it.
    """
    planned = _dig(plan, "request", "port")
    if planned is None:
        return unobserved("the plan names no port for this instance")

    bound = reading["bound"]
    if not bound:
        return failed("listening on nothing at all", f"port {planned}")

    ports = sorted({entry["port"] for entry in bound})
    observed = ", ".join(f"{entry['address']}:{entry['port']}" for entry in bound)
    expected = f"port {planned}"

    if ports != [planned]:
        return failed(observed, expected)
    return passed(observed, expected)


def judge_connection(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """An authenticated connection succeeded.

    The one check that proves the instance is usable rather than merely started. Until it
    passes, nothing else on the report means very much.
    """
    del plan
    account = reading.get("account")
    named = f" as {account}" if account else ""
    if reading["accepted"]:
        return passed(f"a connection{named} was accepted", "an authenticated connection succeeds")
    detail = reading.get("detail") or "no reason given"
    return failed(
        f"a connection{named} was refused: {detail}", "an authenticated connection succeeds"
    )


def judge_version(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """The running server is the version the plan asked for.

    Compared on the major version, because that is what a request names and what a support
    matrix is written against. Which part of a version string is the major one is engine
    knowledge, so the role reduces it and this compares what it reduced.
    """
    requested = _dig(plan, "request", "version")
    if requested is None:
        return unobserved("the plan names no version for this instance")

    observed = f"{reading['reported']} (major {reading['major']})"
    if str(reading["major"]) != str(requested):
        return failed(observed, f"major version {requested}")
    return passed(observed, f"major version {requested}")


def judge_parameters(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """Every parameter the plan names reads back with the value the plan gives it.

    Two ways this fails and they are worth telling apart. A parameter that reads back
    differently was overridden by a later configuration file or refused at start-up. A
    parameter the server has never heard of is worse: the plan promises a value nothing
    will ever read, and no amount of running the instance will report it.
    """
    planned = plan.get("parameters")
    if not planned:
        return unobserved("the plan sizes no parameters")

    settings = reading["settings"]
    unknown = list(reading.get("unknown", ()))
    missing = [entry["parameter"] for entry in planned if entry["parameter"] not in settings]
    wrong = [
        f"{name} is {_shown(settings[name])}, planned {_shown(entry['value'])}"
        for entry in planned
        if (name := entry["parameter"]) in settings and not _same(settings[name], entry["value"])
    ]

    total = len(planned)
    expected = f"{total} parameters read back as planned"
    if unknown:
        return failed(
            f"this build of the server has no setting called {', '.join(sorted(unknown))}",
            expected,
        )
    if missing:
        return unobserved(f"the instance was not asked about {', '.join(sorted(missing))}")
    if wrong:
        return failed("; ".join(wrong), expected)
    return passed(f"all {total} read back as planned", expected)


def judge_paths(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """The instance stores what it stores where the plan put it.

    Asked of the running instance rather than of the filesystem. A directory sitting at the
    planned path proves that apply created a directory; that the instance is writing into
    it is a different claim, and the one worth making.
    """
    paths = _dig(plan, "layout", "paths")
    if not paths:
        return unobserved("the plan places no paths")

    planned = {entry["purpose"]: entry["path"] for entry in paths}
    resolved = reading["resolved"]

    unasked = sorted(set(planned) - set(resolved))
    wrong = [
        f"{purpose} is at {resolved[purpose]}, planned {path}"
        for purpose, path in sorted(planned.items())
        if purpose in resolved and resolved[purpose] != path
    ]

    if wrong:
        return failed("; ".join(wrong), f"{len(planned)} paths as the plan places them")
    if not resolved:
        return unobserved("the instance reported none of its own paths")
    settled = len(planned) - len(unasked)
    observed = f"{settled} of {len(planned)} paths are where the plan places them"
    if unasked:
        # Not a failure. Some purposes -- a backup destination the engine has no notion of
        # -- are places the plan puts things rather than places the instance knows about,
        # and the check that proves those is `backup`.
        observed += f"; the instance has no notion of {', '.join(unasked)}"
    return passed(observed, f"{len(planned)} paths as the plan places them")


def judge_log(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """The instance is writing a log, and writing it where the plan puts it."""
    del plan
    path = reading["path"]
    if not reading["exists"]:
        return failed(f"there is no log at {path}", "a log that has been written to")
    if not reading["written_since_start"]:
        return failed(
            f"{path} exists and has not been written to since the service started",
            "a log that has been written to",
        )
    size = reading.get("size_bytes")
    grown = f", {size} bytes" if size is not None else ""
    return passed(
        f"{path} has been written to since start{grown}", "a log that has been written to"
    )


def judge_backup(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """The account the instance runs as can write where the plan puts backups.

    Asked rather than tried. Verify changes nothing, so the role puts the question to the
    kernel as the service account instead of writing a probe file -- which answers for the
    mode, the ownership and a read-only mount all at once, and leaves nothing behind on a
    machine somebody is going to back up.
    """
    del plan
    path = reading["path"]
    if reading["writable"]:
        return passed(f"{path} is writable by the service account", "a writable backup path")
    detail = reading.get("detail")
    said = f": {detail}" if detail else ""
    return failed(f"{path} is not writable by the service account{said}", "a writable backup path")


def judge_auth(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """No rule grants access without a password from anywhere but the machine itself.

    What a method is called is the engine's vocabulary and the role carries it through
    untranslated, so that the report names the rule somebody has to go and delete. Whether
    it requires a password, and whether it is reachable from off the machine, are the two
    things the role has already decided and this compares.
    """
    del plan
    rules = reading["rules"]
    if not rules:
        return unobserved("the instance reported no authentication rules at all")

    open_rules = [
        f"{rule['method']} from {rule.get('address') or 'anywhere'}"
        for rule in rules
        if not rule["password_required"] and not rule["local"]
    ]
    expected = "no password-free rule reachable from off the machine"
    if open_rules:
        return failed(", ".join(open_rules), expected)
    return passed(f"{len(rules)} rules, none of them password-free off the machine", expected)


def judge_account(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """Every account that can log in has a password set.

    Not whether the password is a common one. Finding that out means guessing passwords
    against a live instance, and a verification step that attacks the thing it is verifying
    is a worse idea than the gap it would close.
    """
    del plan
    roles = reading["roles"]
    if not roles:
        return unobserved("the instance reported no accounts at all")

    naked = sorted(role["name"] for role in roles if role["can_login"] and not role["password_set"])
    logins = sum(1 for role in roles if role["can_login"])
    expected = "every account that can log in has a password"
    if naked:
        noun = "account has" if len(naked) == 1 else "accounts have"
        return failed(f"{', '.join(naked)}: {len(naked)} {noun} no password", expected)
    said = (
        "1 account can log in, with a password"
        if logins == 1
        else (f"{logins} accounts can log in, all of them with a password")
    )
    return passed(said, expected)


def judge_initialization(plan: Mapping[str, Any], reading: Mapping[str, Any]) -> Finding:
    """The instance was created with what the plan said it would be created with.

    The one check on the list whose failure cannot be corrected in place. Everything else
    here is a configuration file away from being right; these were fixed when the instance
    was created, and putting them right means dumping everything in it and reloading.
    """
    promised = plan.get("initialization")
    if not promised:
        return unobserved("the plan says nothing about how the instance is created")

    wanted: dict[str, Any] = {
        entry["name"]: entry["value"] for entry in promised.get("settings", ())
    }
    if promised.get("locale") is not None:
        wanted["locale"] = promised["locale"]

    found = dict(reading["settings"])
    if reading.get("locale") is not None:
        found["locale"] = reading["locale"]

    unasked = sorted(set(wanted) - set(found))
    wrong = [
        f"{name} is {_shown(found[name])}, planned {_shown(value)}"
        for name, value in sorted(wanted.items())
        if name in found and not _same(found[name], value)
    ]

    expected = ", ".join(f"{name}={_shown(value)}" for name, value in sorted(wanted.items()))
    if wrong:
        return failed("; ".join(wrong), expected)
    if unasked:
        return unobserved(f"the instance was not asked about {', '.join(unasked)}")
    return passed(f"created with {expected}", expected)


#: Every kind the core can decide, and the whole of it. The keys are exactly the enum in
#: ``schema/verify.schema.json``, which a test holds the two sides of: a kind a profile can
#: name and nothing can judge would be a check that silently never ran.
JUDGEMENTS: Mapping[str, Callable[[Mapping[str, Any], Mapping[str, Any]], Finding]] = {
    "service": judge_service,
    "port": judge_port,
    "connection": judge_connection,
    "version": judge_version,
    "parameters": judge_parameters,
    "paths": judge_paths,
    "log": judge_log,
    "backup": judge_backup,
    "auth": judge_auth,
    "account": judge_account,
    "initialization": judge_initialization,
}


# ------------------------------------------------------------------------------- helpers


def loopback_only(bound: Sequence[Mapping[str, Any]]) -> bool:
    """Whether every socket the instance holds is one only this machine can reach.

    Derived rather than observed, because it is the shape a profile's expression can
    actually read: the expression language has no comprehensions on purpose, so a question
    about a list has to be answered before the expression sees it.
    """
    return bool(bound) and all(entry["address"] in _LOOPBACK for entry in bound)


def _same(observed: Any, planned: Any) -> bool:
    """Whether a value read back is the value the plan gave.

    Numbers compare as numbers and everything else compares as itself. The one thing this
    does not do is coerce a string to a number: a server that answered ``"on"`` where the
    plan says ``true`` has been asked in the wrong units, and quietly agreeing with it here
    would hide that in the one place nobody would look.
    """
    if isinstance(observed, bool) or isinstance(planned, bool):
        return observed is planned
    if isinstance(observed, int | float) and isinstance(planned, int | float):
        return float(observed) == float(planned)
    return bool(observed == planned)


def _shown(value: Any) -> str:
    """One value as a report writes it, so two of them read as a comparison."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _dig(document: Mapping[str, Any], *keys: str) -> Any:
    """Read a nested key, or None if any step of the way is not there."""
    current: Any = document
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current
