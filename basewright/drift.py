"""Whether the host is still the machine the plan was built from.

A plan is a set of decisions about a machine as it was at one moment. Apply runs later --
minutes later, or a fortnight later after somebody approved it -- and the machine may not
be that one any more. So the first thing apply does is look again and compare, and refuse
rather than configure a host the plan no longer describes.

The comparison is against the plan's own ``host`` section, and it cannot be against
anything else: apply reads the plan and nothing else, so what it can notice is exactly what
the plan wrote down. That is a real limit and it is stated rather than papered over --
:data:`UNCHECKED` names what a plan does not carry and what therefore goes unnoticed here.

Two kinds of fact drift differently, and lumping them together is what makes a drift check
either useless or unusable.

* **Identity.** What the machine *is*: its operating system, its architecture, the
  filesystem under a path, whether that filesystem spins. Every one of these was read by a
  rule reaching a verdict or by a rule computing a value, and any change to one is a
  different machine. These must match exactly.
* **Capacity.** How much of something there is: cores and memory. These can be taken away
  from a virtual machine between the plan and the apply, and every sized value was computed
  from what the machine had at the time -- so they drift when they *shrink*, and growth is
  not drift. A host that has been given more memory is still one this plan fits.

Free space is deliberately in neither list, and it is the interesting omission. It is a
capacity fact, a blocking rule reads it, and it looks like the first thing a drift check
should catch. It is left out because **apply consumes it**: installing the packages and
creating the instance is exactly what makes a filesystem smaller, so a second run comparing
against the numbers in the plan would report its own work as drift and refuse to be
idempotent. Answering it properly means asking whether the host still clears the floor the
profile requires, and that floor is in the profile, which apply does not read. So it is
checked once, by a blocking gate, before the plan exists.

Nothing here decides what to do about a difference. It reports what changed, in the words a
person needs to see it, and the step that called it decides whether to go on.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from basewright.units import render_bytes

__all__ = ["UNCHECKED", "Difference", "differences"]

#: What a plan does not carry, and therefore what re-reading the host cannot notice. The
#: list is here rather than in a comment because it is the honest half of what this module
#: does: a drift check is only as wide as the record it compares against, and somebody
#: relying on this is entitled to know where it stops looking.
UNCHECKED: tuple[str, ...] = (
    "the services installed on the host, which the plan does not carry -- an engine "
    "installed by somebody else since the plan was made is found by the packaging, not here",
    "the ports something is listening on, which the plan does not carry -- a port taken "
    "since the plan was made is found when the service fails to bind",
    "the locales the host has, the kernel settings, and the state of its firewall",
    "free space, which apply itself consumes -- a filesystem is smaller after an install "
    "than before one, so comparing it here would make a second run refuse its own work",
)

#: Facts about what the machine is. A change to any of them is a different machine, and
#: every one was read by a rule that reached a verdict or computed a value.
_IDENTITY: tuple[tuple[str, str], ...] = (
    ("os.family", "operating system family"),
    ("os.distro", "distribution"),
    ("os.version", "distribution version"),
    ("arch", "architecture"),
)

#: Facts about how much there is. Growth is not drift; shrinking is.
_CAPACITY: tuple[tuple[str, str], ...] = (
    ("cpu.cores", "cores"),
    ("memory.total_bytes", "memory"),
)

#: Which of these are counts of bytes, so a difference is reported in the units a person
#: reads rather than as a number nobody can hold in their head.
_IN_BYTES: frozenset[str] = frozenset({"memory.total_bytes"})


@dataclass(frozen=True)
class Difference:
    """One way the host is no longer the machine the plan was built from."""

    #: The fact, named the way the plan names it.
    fact: str
    #: What the plan recorded.
    planned: str
    #: What the host says now.
    observed: str
    #: Why this one matters, in a sentence somebody reading a refusal can act on.
    consequence: str

    def __str__(self) -> str:
        return f"{self.fact}: planned {self.planned}, now {self.observed} -- {self.consequence}"


def differences(planned: Mapping[str, Any], observed: Mapping[str, Any]) -> list[Difference]:
    """Every material way ``observed`` is not the host ``planned`` describes.

    Both are the ``host`` section of a plan: the one the plan carries, and the one built
    from facts collected just now. Comparing like with like is deliberate -- there is one
    definition of what a plan records about a machine, and the drift check reads it rather
    than a second, slightly different view of the same host.

    An empty list means the machine is still the one the decisions were made about.
    """
    found: list[Difference] = []
    found.extend(_identity(planned, observed))
    found.extend(_capacity(planned, observed))
    found.extend(_storage(planned.get("storage", ()), observed.get("storage", ())))
    return found


def _identity(planned: Mapping[str, Any], observed: Mapping[str, Any]) -> list[Difference]:
    found = []
    for fact, noun in _IDENTITY:
        before, now = _at(planned, fact), _at(observed, fact)
        if before is None or now is None or before == now:
            continue
        found.append(
            Difference(
                fact=fact,
                planned=str(before),
                observed=str(now),
                consequence=(
                    f"this is a different machine, or a rebuilt one. The {noun} decided "
                    "which version is supported and how everything below it was sized, so "
                    "the plan describes a host that is not this one."
                ),
            )
        )
    return found


def _capacity(planned: Mapping[str, Any], observed: Mapping[str, Any]) -> list[Difference]:
    found = []
    for fact, noun in _CAPACITY:
        before, now = _at(planned, fact), _at(observed, fact)
        if not isinstance(before, int) or not isinstance(now, int) or now >= before:
            continue
        found.append(
            Difference(
                fact=fact,
                planned=_amount(fact, before),
                observed=_amount(fact, now),
                consequence=(
                    f"the host has less {noun} than it had. Every sized value was computed "
                    "from what it had then, so applying this plan would size the instance "
                    "for a machine larger than the one it is going onto."
                ),
            )
        )
    return found


def _storage(
    planned: Sequence[Mapping[str, Any]],
    observed: Sequence[Mapping[str, Any]],
) -> list[Difference]:
    """The filesystems, matched by mount point.

    A mount the plan named and the host no longer reports is the loudest of these: every
    path the plan places was placed on one of them, and a path on a filesystem that is not
    there is a data directory about to be created on the root volume.
    """
    current = {str(entry["mount"]): entry for entry in observed}
    found = []
    for entry in planned:
        mount = str(entry["mount"])
        now = current.get(mount)
        if now is None:
            found.append(
                Difference(
                    fact=f"storage {mount}",
                    planned="a filesystem of its own",
                    observed="not mounted",
                    consequence=(
                        "a path this plan places lives here. Creating it now would put it "
                        "on whatever filesystem covers the directory instead, which is how "
                        "a data directory ends up on the root volume."
                    ),
                )
            )
            continue
        found.extend(_one_filesystem(mount, entry, now))
    return found


def _one_filesystem(
    mount: str,
    planned: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> list[Difference]:
    found = []
    for key, noun, consequence in (
        (
            "filesystem",
            "filesystem",
            "the filesystem was checked against the ones this engine is normally run on, "
            "and it is not the one that was checked.",
        ),
        (
            "rotational",
            "storage type",
            "whether storage spins decides how random reads are costed, so parameters in "
            "this plan were sized for storage this host no longer has.",
        ),
    ):
        before, now = planned.get(key), observed.get(key)
        if before is None or now is None or before == now:
            continue
        found.append(
            Difference(
                fact=f"storage {mount} {noun}",
                planned=_rendered(before),
                observed=_rendered(now),
                consequence=consequence,
            )
        )

    return found


def _at(document: Mapping[str, Any], path: str) -> Any:
    """One fact, by the dotted name the plan writes it under."""
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _amount(fact: str, value: int) -> str:
    return render_bytes(value) if fact in _IN_BYTES else str(value)


def _rendered(value: Any) -> str:
    if isinstance(value, bool):
        return "rotational" if value else "solid state"
    return str(value)
