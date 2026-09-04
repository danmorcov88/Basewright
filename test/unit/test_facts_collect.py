"""Reading what a machine printed.

Every sample here was taken from a real host or a real container, because the failure
this module has is not a crash: it is reading a line slightly wrong and handing the gate
engine a host that does not exist. A parser tested only against output somebody imagined
is a parser tested against the wrong thing.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from basewright.facts import collect, normalize

# ------------------------------------------------------------------------ sockets

#: Real ``ss -H -lntupn`` output. The first line came off a container running a listener;
#: the rest are the forms a server produces that the first one does not cover.
SS_OUTPUT = """\
tcp LISTEN 0      5      0.0.0.0:8080 0.0.0.0:* users:(("python3",pid=94,fd=3))
tcp LISTEN 0      4096   127.0.0.53%lo:53 0.0.0.0:* users:(("systemd-resolve",pid=1,fd=13))
tcp LISTEN 0      4096   [::1]:6010 [::]:*
udp UNCONN 0      0      0.0.0.0:68 0.0.0.0:* users:(("dhclient",pid=612,fd=6))
tcp LISTEN 0      128    *:22 *:* users:(("sshd",pid=800,fd=3))
"""


def test_every_socket_is_read() -> None:
    found = collect.listening_ports(SS_OUTPUT)
    assert [socket["port"] for socket in found] == [8080, 53, 6010, 68, 22]


def test_a_socket_carries_what_holds_it() -> None:
    """The rule reporting an occupied port names the process, because 'something is on
    5432' and 'the thing you are installing is already on 5432' are different problems."""
    found = collect.listening_ports(SS_OUTPUT)
    assert found[0]["process"] == "python3"
    assert "process" not in found[2], "no holder was shown, so none is invented"


def test_protocol_is_read_from_the_line_rather_than_assumed() -> None:
    found = collect.listening_ports(SS_OUTPUT)
    assert [socket["protocol"] for socket in found] == ["tcp", "tcp", "tcp", "udp", "tcp"]


def test_an_address_is_written_the_way_a_person_would_type_it() -> None:
    found = collect.listening_ports(SS_OUTPUT)
    assert found[2]["address"] == "::1", "the brackets are notation, not part of the address"
    assert found[4]["address"] == "0.0.0.0", "* is how ss writes every address"


def test_nothing_listening_is_not_a_failure() -> None:
    """A host with no listeners is ordinary. It is also what a fresh container looks like."""
    assert collect.listening_ports("") == []


def test_a_line_that_cannot_be_read_is_skipped_rather_than_guessed_at() -> None:
    assert collect.listening_ports("tcp LISTEN 0 128 nonsense\ngarbage\n") == []


# ----------------------------------------------------------------------- services

#: The shape ``service_facts`` returns, with the two things a real host does that a
#: made-up sample would not: a unit suffix, and two init systems answering about one
#: service. Both were observed on Debian 12 in the molecule scenario.
SERVICE_FACTS: dict[str, dict[str, Any]] = {
    "ssh.service": {"name": "ssh.service", "state": "running", "source": "systemd"},
    "procps.service": {"name": "procps.service", "state": "stopped", "source": "systemd"},
    "procps": {"name": "procps", "state": "running", "source": "sysv"},
    "rescue.service": {"name": "rescue.service", "state": "inactive", "source": "systemd"},
}


def test_a_unit_suffix_is_not_part_of_a_service_name() -> None:
    """A profile declares what conflicts with it in the name a person uses."""
    assert [service["name"] for service in collect.services(SERVICE_FACTS)] == [
        "procps",
        "rescue",
        "ssh",
    ]


def test_two_init_systems_describing_one_service_produce_one_entry() -> None:
    found = {service["name"]: service["state"] for service in collect.services(SERVICE_FACTS)}
    assert found["procps"] == "running", "a service somebody can see running is running"


def test_a_state_nobody_recognises_still_means_installed() -> None:
    """The dangerous direction is a service disappearing from the list: that is what makes
    a conflict rule pass on a host already running the thing being provisioned."""
    found = {service["name"]: service["state"] for service in collect.services(SERVICE_FACTS)}
    assert found["rescue"] == "installed"


def test_the_list_is_ordered_so_two_runs_can_be_compared() -> None:
    names = [service["name"] for service in collect.services(SERVICE_FACTS)]
    assert names == sorted(names)


# ------------------------------------------------------------------------- kernel


def slurped(path: str, content: str) -> dict[str, Any]:
    return {"item": path, "content": base64.b64encode(content.encode()).decode()}


def test_the_active_huge_page_mode_is_the_one_in_brackets() -> None:
    assert collect.transparent_hugepages("always [madvise] never\n") == "madvise"
    assert collect.transparent_hugepages("[always] madvise never\n") == "always"


def test_a_huge_page_file_that_says_nothing_useful_is_not_an_answer() -> None:
    assert collect.transparent_hugepages("") is None


def test_the_kernel_settings_a_rule_reads_are_collected_together() -> None:
    assert collect.kernel_settings(
        [
            slurped("/proc/sys/vm/swappiness", "60\n"),
            slurped("/proc/sys/vm/overcommit_memory", "1\n"),
            slurped("/sys/kernel/mm/transparent_hugepage/enabled", "always [madvise] never\n"),
        ]
    ) == {"swappiness": 60, "overcommit_memory": 1, "transparent_hugepages": "madvise"}


def test_a_file_the_host_would_not_read_is_left_out_rather_than_defaulted() -> None:
    assert collect.kernel_settings(
        [
            {"item": "/proc/sys/vm/swappiness", "failed": True},
            slurped("/proc/sys/vm/overcommit_memory", "0\n"),
        ]
    ) == {"overcommit_memory": 0}


def test_a_host_that_answered_nothing_reports_no_kernel_section() -> None:
    """An empty object would say the host was asked and had nothing to say, which is the
    opposite of what a missing file means."""
    assert collect.kernel_settings([{"item": "/proc/sys/vm/swappiness", "failed": True}]) is None


# ---------------------------------------------------------------------- time sync

#: ``timedatectl show`` on a synchronized Ubuntu host.
TIMEDATECTL = """\
Timezone=Etc/UTC
LocalRTC=no
CanNTP=yes
NTP=yes
NTPSynchronized=yes
TimeUSec=Thu 2026-09-04 07:52:32 UTC
"""


def test_a_disciplined_clock_names_what_is_disciplining_it() -> None:
    assert collect.time_sync(TIMEDATECTL) == {
        "service": "systemd-timesyncd",
        "synchronized": True,
    }


def test_a_clock_nothing_is_keeping_right_is_a_different_report() -> None:
    output = TIMEDATECTL.replace("NTP=yes", "NTP=no").replace(
        "NTPSynchronized=yes", "NTPSynchronized=no"
    )
    assert collect.time_sync(output) == {"service": "none", "synchronized": False}


def test_a_host_with_no_message_bus_reports_no_clock_at_all() -> None:
    """Which is what a container says, and it is the correct answer: nobody asked the
    clock anything, so the rule that reads this skips rather than warning."""
    assert collect.time_sync("Failed to connect to bus: No such file or directory\n") is None


# ----------------------------------------------------------------------- firewall

#: ``ufw status`` with rules, as a host with a firewall prints it.
UFW_ACTIVE = """\
Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere
5432                       ALLOW       10.0.0.0/8
6000:6010/tcp              ALLOW       Anywhere
OpenSSH                    ALLOW       Anywhere
22/tcp (v6)                ALLOW       Anywhere (v6)
"""


def test_an_active_firewall_reports_the_ports_it_admits() -> None:
    assert collect.ufw_firewall(UFW_ACTIVE) == {
        "service": "ufw",
        "active": True,
        "open_ports": [22, 5432],
    }


def test_a_rule_this_cannot_read_narrows_the_answer_rather_than_widening_it() -> None:
    """A range and a named service are skipped. Reporting fewer open ports than a host has
    makes the rule warn where it need not, which is the safe direction for a rule nobody
    may override."""
    admitted = collect.ufw_firewall(UFW_ACTIVE)
    assert admitted is not None
    assert 6000 not in admitted["open_ports"]


def test_an_inactive_firewall_is_still_an_answer() -> None:
    assert collect.ufw_firewall("Status: inactive\n") == {
        "service": "ufw",
        "active": False,
        "open_ports": [],
    }


def test_a_host_with_no_firewall_installed_reports_none() -> None:
    """Rather than an unfiltered host, which is what a collector that did not recognise
    the filter would be claiming."""
    assert collect.ufw_firewall("") is None
    assert collect.ufw_firewall("sh: 1: ufw: not found\n") is None


# ------------------------------------------------------------------------- mounts

#: ``ansible_facts.mounts`` from a real machine, plus the pseudo-filesystem that has no
#: size and the entry whose device the kernel describes under another name.
ANSIBLE_MOUNTS: list[dict[str, Any]] = [
    {
        "mount": "/var/lib/data",
        "device": "/dev/nvme0n1p2",
        "fstype": "xfs",
        "options": "rw,noatime,attr2",
        "size_total": 1081101176832,
        "size_available": 999963688960,
    },
    {
        "mount": "/",
        "device": "/dev/sda1",
        "fstype": "ext4",
        "options": "rw,relatime",
        "size_total": 53687091200,
        "size_available": 21474836480,
    },
    {"mount": "/proc", "device": "proc", "fstype": "proc", "options": "rw", "size_total": 0},
]

ANSIBLE_DEVICES: dict[str, dict[str, Any]] = {
    "sda": {"rotational": "1"},
    "nvme0n1": {"rotational": "0"},
}


def test_mounts_are_ordered_by_path() -> None:
    found = collect.mounts(ANSIBLE_MOUNTS, ANSIBLE_DEVICES)
    assert [mount["path"] for mount in found] == ["/", "/var/lib/data"]


def test_a_filesystem_with_no_size_is_not_somewhere_a_database_can_live() -> None:
    found = collect.mounts(ANSIBLE_MOUNTS, ANSIBLE_DEVICES)
    assert "/proc" not in [mount["path"] for mount in found]


def test_options_are_split_into_the_list_the_contract_asks_for() -> None:
    found = collect.mounts(ANSIBLE_MOUNTS, ANSIBLE_DEVICES)
    assert found[1]["options"] == ["rw", "noatime", "attr2"]


@pytest.mark.parametrize(
    "device,expected",
    [
        ("/dev/sda1", True),
        ("/dev/sda", True),
        ("/dev/nvme0n1p2", False),
        ("/dev/mapper/vg-data", None),
        ("overlay", None),
    ],
)
def test_a_partition_is_matched_back_to_the_disk_it_sits_on(
    device: str, expected: bool | None
) -> None:
    assert collect.rotational_for(device, ANSIBLE_DEVICES) is expected


# ------------------------------------------------------------------------- memory


def test_available_memory_is_read_rather_than_free_memory() -> None:
    """MemFree on a busy server is almost always small and almost always irrelevant. A
    headroom rule reading it would warn about every healthy machine it ever saw."""
    meminfo = (
        "MemTotal:       16235692 kB\nMemFree:          204800 kB\nMemAvailable:   14676844 kB\n"
    )
    assert collect.available_bytes(meminfo) == 14676844 * 1024


def test_a_kernel_too_old_to_report_it_says_so_rather_than_guessing() -> None:
    assert collect.available_bytes("MemTotal: 16235692 kB\n") is None


def test_the_processor_model_is_the_one_thing_in_the_list_that_is_not_a_number() -> None:
    processor = ["0", "GenuineIntel", "12th Gen Intel(R) Core(TM) i5-12500", "1", "GenuineIntel"]
    assert collect.processor_model(processor) == "12th Gen Intel(R) Core(TM) i5-12500"


def test_a_machine_that_described_no_processor_is_not_given_one() -> None:
    assert collect.processor_model([]) is None
    assert collect.processor_model(["0", "1", "2"]) is None


# ------------------------------------------------ the document, end to end

#: What the role registers, with every value taken from a real molecule run against
#: Ubuntu 24.04. Trimmed to the keys the assembly reads, because the rest of what
#: ``setup`` returns is several hundred fields nothing here looks at.
COLLECTED: dict[str, Any] = {
    "host": "gather-ubuntu2404",
    "facts": {
        "date_time": {"iso8601": "2026-09-04T07:52:32Z"},
        "os_family": "Debian",
        "distribution": "Ubuntu",
        "distribution_version": "24.04",
        "distribution_release": "noble",
        "lsb": {"description": "Ubuntu 24.04.4 LTS"},
        "kernel": "6.8.0-45-generic",
        "architecture": "x86_64",
        "processor_nproc": 12,
        "processor_vcpus": 12,
        "processor": ["0", "GenuineIntel", "12th Gen Intel(R) Core(TM) i5-12500"],
        "memtotal_mb": 15855,
        "swaptotal_mb": 4096,
        "mounts": ANSIBLE_MOUNTS,
        "devices": ANSIBLE_DEVICES,
        "services": SERVICE_FACTS,
        "user_id": "root",
    },
    "sockets": SS_OUTPUT,
    "locales": ["en_US.utf8", "C.UTF-8", "POSIX", "C"],
    "kernel": [slurped("/proc/sys/vm/swappiness", "60\n")],
    "meminfo": "MemTotal: 16235692 kB\nMemAvailable: 14676844 kB\n",
    "timedate": TIMEDATECTL,
    "ufw": UFW_ACTIVE,
    "escalation": {"rc": 0, "stdout": "0\n"},
}


def test_the_collected_document_is_one_the_core_accepts() -> None:
    """The whole point of the arrangement. A collector the core refuses is a collector
    nobody finds out about until a plan is wanted on a Friday afternoon."""
    host = normalize(collect.document(COLLECTED))

    assert host.host == "gather-ubuntu2404"
    assert host.os.family == "debian"
    assert host.cpu.cores == 12
    assert host.memory.total_bytes == 15855 * collect.MIB


def test_the_document_is_lowercased_where_the_contract_says_lowercase() -> None:
    """The core canonicalizes casing before validating, so an uppercase family would be
    accepted anyway. Depending on that would mean depending on something the contract
    never promised."""
    written = collect.document(COLLECTED)

    assert written["os"]["family"] == "debian"
    assert written["os"]["distro"] == "ubuntu"
    assert written["arch"] == "x86_64"


def test_a_fact_nobody_could_collect_is_absent_rather_than_null() -> None:
    """Absent means nobody asked and the rule skips. A null would be an answer."""
    silent = {**COLLECTED, "timedate": "", "ufw": "", "kernel": []}
    written = collect.document(silent)

    assert "time_sync" not in written
    assert "firewall" not in written
    assert "kernel" not in written
    assert normalize(written).time_sync is None


def test_the_repositories_a_host_reached_are_never_claimed_here() -> None:
    """Which ones to try comes from the profile, so it is the one fact whose collection
    depends on knowing what is being provisioned. Absent means nobody asked; present and
    empty would mean the host was asked and reached nothing, which blocks."""
    assert "reachable_repositories" not in collect.document(COLLECTED)


def test_a_host_that_cannot_escalate_says_so() -> None:
    """A key that works and a sudo rule that does not is the failure that otherwise
    surfaces halfway through an apply."""
    refused = {**COLLECTED, "escalation": {"rc": 1, "stdout": ""}}
    assert normalize(collect.document(refused)).privileges.can_escalate is False


def test_locales_are_ordered_so_two_collections_can_be_compared() -> None:
    written = collect.document(COLLECTED)
    assert written["locales"] == sorted(written["locales"])


def test_a_host_without_lsb_still_gets_a_readable_name() -> None:
    plain = {**COLLECTED, "facts": {**COLLECTED["facts"], "lsb": {}}}
    assert collect.document(plain)["os"]["pretty_name"] == "Ubuntu 24.04"
