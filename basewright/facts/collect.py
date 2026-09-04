"""Turning what a machine printed into the document the facts contract expects.

The reading is Ansible's job: it runs over SSH, and reaching a host is what Ansible is
for. Deciding what a line of ``ss`` output means is not. Parsing fails in ways nobody
notices until a gate reaches the wrong verdict on a real machine, and a template is a bad
place to be wrong in -- so the playbook runs the commands, and this module reads them,
which puts every line that could be wrong under pytest with the output of a real host
beside it.

The role's template is therefore one line long. That is the point of the arrangement
rather than a happy accident: the boundary between the half that acts and the half that
decides is not a place to leave a second implementation of anything.

Nothing here reaches a verdict or applies a threshold. A function in this module answers
*what did the host say*; what the answer means is decided later, by a rule that ships with
the reason it exists.

Two habits run through all of it:

* **Unreadable is not empty.** A line these functions cannot parse is skipped. A command
  that answered nothing at all is a different thing from a host with nothing to report,
  and the caller is left able to tell them apart.
* **Absent is not false.** Where a machine could not answer -- a container with no message
  bus, a host with no firewall installed -- the answer is ``None`` and the field is left
  out. The contract reads a missing optional fact as nobody having asked, so the rule that
  wanted it skips and says so instead of guessing.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping, Sequence
from typing import Any

#: Bytes in a mebibyte. Ansible reports memory in whole mebibytes and the contract is
#: written in bytes, so this conversion exists and nothing else does.
MIB = 1024 * 1024

#: ``ss -H -lntupn`` writes one socket per line, whitespace separated:
#:
#:     tcp LISTEN 0 5 0.0.0.0:8080 0.0.0.0:* users:(("python3",pid=94,fd=3))
#:
#: The first field is the protocol and the fifth is the local address and port. The
#: seventh is absent unless the collector could see the process table.
_SS_FIELDS = 6

#: A socket's holders are written as a list. The first name is the one worth reporting: a
#: socket held by several processes is one occupied port either way.
_SS_PROCESS = re.compile(r'users:\(\("([^"]+)"')

#: ``/sys/kernel/mm/transparent_hugepage/enabled`` marks the active mode in brackets --
#: ``always [madvise] never`` -- and the bracket is the whole answer.
_THP_ACTIVE = re.compile(r"\[([a-z]+)\]")

#: ``ufw status`` writes one rule per line with the port first:
#:
#:     8080/tcp                   ALLOW       Anywhere
#:
#: A range or a named service is not a single port and is skipped rather than guessed at.
#: A firewall admitting a range this cannot read reports fewer open ports than it has,
#: which makes the rule reading it warn where it need not. That is the safe direction to
#: be wrong in for a rule nobody may override.
_UFW_PORT = re.compile(r"^(\d+)(?:/(?:tcp|udp))?\s")

#: A mount names a partition and the kernel describes a disk, so ``/dev/sda1`` has to lose
#: its partition before ``devices`` recognises it. NVMe and device mapper number their
#: partitions after a ``p``; everything else appends digits directly.
_PARTITION = re.compile(r"(p?\d+)$")


def listening_ports(output: str) -> list[dict[str, Any]]:
    """What is listening, from ``ss -H -lntupn``.

    The port an instance wants has to be free, and free means nothing answers on it. That
    is a question about sockets rather than about services: a process holding a port
    without a service unit behind it holds the port just as firmly.
    """
    found: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < _SS_FIELDS:
            continue

        address, _, port = fields[4].rpartition(":")
        if not port.isdigit():
            continue

        socket: dict[str, Any] = {
            "port": int(port),
            # ``*`` is how ss writes "every address", and the contract prefers the form a
            # person would type. An IPv6 address arrives bracketed, and the brackets
            # belong to the notation rather than to the address.
            "address": "0.0.0.0" if address in {"*", ""} else address.strip("[]"),
            "protocol": "udp" if fields[0].startswith("udp") else "tcp",
        }
        holder = _SS_PROCESS.search(line)
        if holder is not None:
            socket["process"] = holder.group(1)
        found.append(socket)

    return found


#: What ``service_facts`` calls a state, in the contract's vocabulary. It reports several
#: others, because it covers more init systems than this project will ever meet, and all
#: of them mean the unit is present without the host saying whether it runs. That is still
#: an installation, and an installation is what a conflict rule is looking for.
_SERVICE_STATES: Mapping[str, str] = {"running": "running", "stopped": "stopped"}

#: How definite each state is. A host running both systemd and a compatibility layer
#: answers twice about the same service, and the two answers can disagree: one enumerates
#: a unit file it has never started, the other watches the process. Running beats stopped
#: beats merely present, because a service somebody can see running is running.
_STATE_CONFIDENCE: tuple[str, ...] = ("installed", "stopped", "running")


def services(collected: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """What is installed, from ``ansible.builtin.service_facts``.

    The module is used rather than ``systemctl`` parsed, because enumerating services
    across init systems is a solved problem and solving it again here would mean owning a
    worse version of it.

    What is deliberately absent is any judgement about which of these matters. The core
    recognises no service by name; a profile declares what conflicts with it, and this
    function's whole job is to hand that rule a complete list to match against. A short
    list is the dangerous failure: it is what makes a conflict rule pass on a host already
    running the thing being provisioned.
    """
    states: dict[str, str] = {}
    for unit, service in collected.items():
        # ``service_facts`` keys by unit name, suffix included. The suffix says which init
        # system answered, which is not part of a service's identity and not something a
        # conflict rule matches on -- so two init systems describing one service collapse
        # into the one service they are both describing.
        name = unit.removesuffix(".service")
        state = _SERVICE_STATES.get(str(service.get("state", "")).lower(), "installed")
        known = states.get(name)
        if known is None or _STATE_CONFIDENCE.index(state) > _STATE_CONFIDENCE.index(known):
            states[name] = state

    return [{"name": name, "state": states[name]} for name in sorted(states)]


def transparent_hugepages(setting: str) -> str | None:
    """Which huge page mode is active, from the sysfs file that lists all of them."""
    match = _THP_ACTIVE.search(setting)
    return match.group(1) if match is not None else None


def kernel_settings(slurped: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """The kernel settings a rule reads, from a loop of ``slurp`` results.

    Each is read from its own file and any of them can be missing, so they are assembled
    together rather than field by field: an empty ``kernel`` object would claim the host
    was asked and had nothing to say, which is the opposite of what a missing file means.
    """
    files = {
        str(result["item"]): _decoded(result["content"])
        for result in slurped
        if result.get("content") is not None
    }
    settings: dict[str, Any] = {}

    swappiness = files.get("/proc/sys/vm/swappiness", "").strip()
    if swappiness.isdigit():
        settings["swappiness"] = int(swappiness)

    overcommit = files.get("/proc/sys/vm/overcommit_memory", "").strip()
    if overcommit.isdigit():
        settings["overcommit_memory"] = int(overcommit)

    active = transparent_hugepages(files.get("/sys/kernel/mm/transparent_hugepage/enabled", ""))
    if active is not None:
        settings["transparent_hugepages"] = active

    return settings or None


def time_sync(output: str) -> dict[str, Any] | None:
    """Whether the clock is being kept right, from ``timedatectl show``.

    Absent where the host could not answer, which a container without a message bus cannot.
    That is the correct answer rather than a failure: nobody asked the clock anything, so
    the rule reading this skips instead of warning about a machine it knows nothing about.
    """
    fields = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    if "NTPSynchronized" not in fields:
        return None

    # Which service keeps the clock is the useful half of the report: "the clock is wrong"
    # and "nothing is keeping it right" are different conversations with whoever owns the
    # host, and only the second of them is anybody's fault.
    running = fields.get("NTP", "").strip() == "yes"
    return {
        "service": "systemd-timesyncd" if running else "none",
        "synchronized": fields["NTPSynchronized"].strip() == "yes",
    }


def ufw_firewall(output: str) -> dict[str, Any] | None:
    """What the host filters, from ``ufw status``.

    One firewall is read because one operating system family is in scope. A host running
    something else reports no firewall at all, which the contract treats as nobody having
    asked -- so the rule skips and says so, rather than reporting an unfiltered host
    because the collector did not recognise the filter.
    """
    state: bool | None = None
    ports: list[int] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Status:"):
            state = stripped.partition(":")[2].strip() == "active"
            continue
        match = _UFW_PORT.match(stripped)
        if match is not None:
            ports.append(int(match.group(1)))

    if state is None:
        return None
    return {"service": "ufw", "active": state, "open_ports": sorted(set(ports))}


def rotational_for(
    device: str,
    devices: Mapping[str, Mapping[str, Any]],
    uuid: str | None = None,
) -> bool | None:
    """Whether a mount's device spins, from ``ansible_facts.devices``.

    No gate reads this, and two sizing rules do -- and a sizing rule that reads an
    unreported fact refuses the plan rather than guessing at it. So an answer this cannot
    reach is a host that gets no plan, which makes the difference between the forms a
    mount table writes a device in worth taking seriously.

    A mount names whatever was mounted and the kernel describes what is underneath, and
    the two rarely spell it the same way. Three things are tried, in the order they are
    cheap:

    * **The name, with any partition suffix removed.** ``/dev/sda1`` is a partition of the
      disk ``sda``, and it is the disk that spins or does not.
    * **The filesystem's own uuid**, against the ``/dev/disk/by-uuid`` links the kernel
      reports for each device. This is what resolves everything else, because it does not
      care how the mount was named: ``/dev/mapper/vg0-data``, ``/dev/vg0/data`` and
      ``UUID=...`` in an fstab all arrive at the same device by it.

    Device mapper deserves its own note, because it is the case this exists for. A
    production estate runs on LVM, the mount says ``/dev/mapper/...``, and ``devices``
    describes it as ``dm-0``. The kernel has already done the hard part: a mapped device
    reports itself non-rotational only when everything underneath it is, so reading
    ``dm-0`` is reading the answer for the disks beneath it rather than for an
    abstraction. Descending to those disks by hand would re-derive, slightly worse, what
    the block layer already worked out.

    Where none of that resolves, the answer stays ``None``. Absent is not a guess.
    """
    entry = _device_of(device, devices) or _device_by_uuid(uuid, devices)
    if entry is None or "rotational" not in entry:
        return None
    return str(entry["rotational"]).strip() == "1"


def _device_of(device: str, devices: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """One device by the name a mount used, if the kernel describes it under that name."""
    if not device.startswith("/dev/"):
        return None
    name = device.removeprefix("/dev/")
    for candidate in (name, _PARTITION.sub("", name)):
        entry = devices.get(candidate)
        if entry is not None:
            return entry
    return None


def _device_by_uuid(
    uuid: str | None, devices: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    """One device by the uuid of the filesystem on it.

    ``N/A`` is what a mount reports when there is no uuid to report, and it is a string
    like any other -- so it is excluded by name rather than left to match a device that
    also has nothing.
    """
    if not uuid or uuid == "N/A":
        return None
    for entry in devices.values():
        links = entry.get("links")
        if isinstance(links, Mapping) and uuid in links.get("uuids", ()):
            return entry
    return None


def mounts(
    collected: Sequence[Mapping[str, Any]],
    devices: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The filesystems a host has, from ``ansible_facts.mounts``.

    Mounts with no size are dropped: they are the pseudo-filesystems a kernel presents,
    and a rule asking whether a path has room to hold a database has nothing to say about
    any of them.
    """
    found: list[dict[str, Any]] = []
    for mount in collected:
        total = mount.get("size_total")
        available = mount.get("size_available")
        if not isinstance(total, int) or not isinstance(available, int) or total <= 0:
            continue

        device = str(mount.get("device", ""))
        entry: dict[str, Any] = {
            "path": str(mount["mount"]),
            "filesystem": str(mount["fstype"]),
            "total_bytes": total,
            "free_bytes": available,
        }
        if device:
            entry["device"] = device
        options = [option for option in str(mount.get("options", "")).split(",") if option]
        if options:
            entry["options"] = options
        spins = rotational_for(device, devices, mount.get("uuid"))
        if spins is not None:
            entry["rotational"] = spins
        found.append(entry)

    return sorted(found, key=lambda entry: str(entry["path"]))


def available_bytes(meminfo: str) -> int | None:
    """How much memory a new process could actually get, from ``/proc/meminfo``.

    ``MemAvailable`` rather than ``MemFree``, because free memory on a busy server is
    almost always small and almost always irrelevant: the page cache gives it back under
    pressure. A rule warning about headroom that read ``MemFree`` would warn about every
    healthy machine it ever saw.
    """
    for line in meminfo.splitlines():
        label, _, value = line.partition(":")
        if label.strip() != "MemAvailable":
            continue
        amount = value.strip().split()
        if amount and amount[0].isdigit():
            return int(amount[0]) * 1024
    return None


def processor_model(processor: Sequence[str]) -> str | None:
    """The model name out of ``ansible_facts.processor``.

    The fact is a flat list of whatever the kernel exposed per core -- indices, a vendor
    id, a model name -- with no key saying which is which. The model is the longest entry
    that is not a number, every time, on every machine this has been run against. It is a
    heuristic, and it is applied to a field nothing gates on: a wrong answer here is a
    cosmetic line in a report rather than a decision.
    """
    names = [entry for entry in processor if not str(entry).strip().isdigit()]
    return max(names, key=len) if names else None


def _decoded(content: str) -> str:
    """A ``slurp`` result, which arrives base64 encoded whatever the file held."""
    return base64.b64decode(content).decode("utf-8", errors="replace")


def reached(probes: Sequence[Mapping[str, Any]]) -> list[str]:
    """The repositories the host got an answer from, out of what the probes came back with.

    An HTTP status -- any HTTP status -- is proof that the host resolved the name, opened
    a connection, completed the handshake and was answered. That is the whole of what the
    rule reading this asks. Whether a repository that answered is also well formed is a
    different question, and answering it would mean knowing how each family lays its
    repositories out, which is knowledge this side of the split does not have.

    A probe that never got that far reports no status of its own and is left out. Absent
    from this list is a host that tried and failed, which is a refusal. That is a
    different thing from the list not existing, which is nobody having asked.
    """
    answered: set[str] = set()
    for probe in probes:
        url = probe.get("item")
        status = probe.get("status")
        if isinstance(url, str) and isinstance(status, int) and status > 0:
            answered.add(url)
    return sorted(answered)


def _without_none(values: Mapping[str, Any]) -> dict[str, Any]:
    """Drop what the host did not report, rather than writing it down as a null.

    The contract distinguishes a fact that is absent from one that is present and empty,
    and a null would be neither.
    """
    return {key: value for key, value in values.items() if value is not None}


def document(
    collected: Mapping[str, Any],
    probes: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Everything a host reported, as the contract writes it down.

    One function rather than a template, so that assembling the document is covered by the
    same tests as parsing it. ``collected`` is what the role registered, handed over
    unchanged; every judgement about what any of it means happens here.

    ``probes`` is the one input that is not the host talking about itself: what came back
    when it was asked to reach the repositories a profile names. ``None`` means nobody
    asked, and the field is left out entirely -- which is not the same document as one
    saying the host reached nothing, and the rule reading it tells the two apart.
    """
    facts: Mapping[str, Any] = collected["facts"]
    escalation: Mapping[str, Any] = collected["escalation"]

    return _without_none(
        {
            "schema_version": "1",
            "collected_at": facts["date_time"]["iso8601"],
            "host": collected["host"],
            "os": _without_none(
                {
                    # The packaging family is reported, never derived. Working out that one
                    # distribution is packaged like another is knowledge about operating
                    # systems, and it belongs where the observation is made.
                    #
                    # Lowercased here rather than left to the reader. The core canonicalizes
                    # casing before it validates, so an uppercase family would be accepted
                    # -- but the schema says lowercase, and a collector that only works
                    # because the reader tidies up after it is depending on something the
                    # contract never promised.
                    "family": str(facts["os_family"]).lower(),
                    "distro": str(facts["distribution"]).lower(),
                    "version": facts["distribution_version"],
                    "codename": facts.get("distribution_release") or None,
                    "pretty_name": facts.get("lsb", {}).get("description")
                    or f"{facts['distribution']} {facts['distribution_version']}",
                    "kernel": facts.get("kernel"),
                }
            ),
            "arch": str(facts["architecture"]).lower(),
            "cpu": _without_none(
                {
                    # The number of processors the machine will actually schedule on,
                    # rather than a socket count multiplied by cores per socket. It is what
                    # a database will use and what a minimum should be checked against, and
                    # it is the one of the two that a container reports honestly.
                    "cores": facts["processor_nproc"],
                    "threads": facts.get("processor_vcpus"),
                    "model": processor_model(facts.get("processor", [])),
                }
            ),
            "memory": _without_none(
                {
                    "total_bytes": facts["memtotal_mb"] * MIB,
                    "available_bytes": available_bytes(collected["meminfo"]),
                    "swap_bytes": facts.get("swaptotal_mb", 0) * MIB,
                }
            ),
            "mounts": mounts(facts.get("mounts", []), facts.get("devices", {})),
            "network": {"listening_ports": listening_ports(collected["sockets"])},
            "services": services(facts.get("services", {})),
            "locales": sorted(collected["locales"]),
            "reachable_repositories": None if probes is None else reached(probes),
            "privileges": {
                "user": facts["user_id"],
                # Not whether the account is root, but whether it can become root here and
                # now. A key that works and a sudo rule that does not is the failure this
                # answers, and it is the one that surfaces halfway through an apply.
                "can_escalate": escalation.get("rc") == 0
                and str(escalation.get("stdout", "")).strip() == "0",
            },
            "time_sync": time_sync(collected["timedate"]),
            "kernel": kernel_settings(collected["kernel"]),
            "firewall": ufw_firewall(collected["ufw"]),
        }
    )
