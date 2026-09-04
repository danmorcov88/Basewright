"""The gather verb: the first one that does something.

It reads a facts document, normalizes it and says what the machine is. What writes that
document is `ansible/playbooks/gather.yml`, which reaches the host and then hands the file
straight back to this verb (ADR-0020) -- so a fixture and a collected host are the same
kind of thing, read by the same code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from basewright.cli import EXIT_OK, EXIT_REFUSED, EXIT_USAGE, main

ROOT = Path(__file__).resolve().parents[2]
HOSTS = ROOT / "test" / "fixtures" / "hosts"


def test_a_host_is_summarised(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["gather", "--facts", str(HOSTS / "typical.json")])

    printed = capsys.readouterr().out
    assert code == EXIT_OK
    assert "db-typical.invalid" in printed
    assert "32.0 GiB" in printed
    assert "8 cores" in printed
    assert "Nothing was changed." in printed


def test_every_mount_is_shown(capsys: pytest.CaptureFixture[str]) -> None:
    """Which filesystems exist is most of what a disk gate is about to decide on."""
    main(["gather", "--facts", str(HOSTS / "large.json")])

    printed = capsys.readouterr().out
    for mount in ("/var/lib/basewright", "/var/log", "/backup", "/mnt/readonly"):
        assert mount in printed


def test_a_clock_out_of_step_is_not_buried(capsys: pytest.CaptureFixture[str]) -> None:
    main(["gather", "--facts", str(HOSTS / "crowded.json")])

    assert "NOT synchronized" in capsys.readouterr().out


def test_the_output_is_ascii(capsys: pytest.CaptureFixture[str]) -> None:
    """The documentation capture is compared byte for byte between this machine and CI,
    and the two do not agree about what a console encoding is."""
    for name in ("typical", "small", "large", "crowded", "rocky"):
        main(["gather", "--facts", str(HOSTS / f"{name}.json")])
        assert capsys.readouterr().out.isascii()


def test_json_emits_the_shape_a_plan_carries(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["gather", "--facts", str(HOSTS / "typical.json"), "--json"])

    emitted = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert emitted["arch"] == "x86_64"
    assert emitted["memory"]["total_bytes"] == 34359738368
    assert len(emitted["storage"]) == 3


def test_json_is_stable_between_runs(capsys: pytest.CaptureFixture[str]) -> None:
    """A plan is diffed against the one from three months ago. Key order is not news."""
    main(["gather", "--facts", str(HOSTS / "typical.json"), "--json"])
    first = capsys.readouterr().out
    main(["gather", "--facts", str(HOSTS / "typical.json"), "--json"])

    assert capsys.readouterr().out == first


def test_facts_are_required_and_the_reason_is_given(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["gather"])

    printed = capsys.readouterr().err
    assert code == EXIT_USAGE
    assert "not built yet" in printed
    assert "STATUS.md" in printed


def test_a_document_that_is_not_there_is_a_usage_error(tmp_path: Path) -> None:
    assert main(["gather", "--facts", str(tmp_path / "nowhere.json")]) == EXIT_USAGE


def test_a_host_that_contradicts_itself_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refused is a first-class outcome with an exit code of its own, not a crash."""
    document = json.loads((HOSTS / "typical.json").read_text(encoding="utf-8"))
    document["cpu"]["threads"] = 1
    broken = tmp_path / "facts.json"
    broken.write_text(json.dumps(document), encoding="utf-8")

    code = main(["gather", "--facts", str(broken)])

    assert code == EXIT_REFUSED
    assert "cpu.threads" in capsys.readouterr().err


# --------------------------------------------------- a host that was actually collected

#: A document the collecting playbook produced against a real container, committed as it
#: came off the run. Every other fixture here was written by hand to exercise a rule; this
#: one exists to prove the collector and the core still describe the same thing, and it is
#: the only one whose contents nobody chose.
COLLECTED = HOSTS / "collected.json"


def test_a_collected_host_is_a_host_like_any_other(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The point of the contract. A document that came off a wire and one written by hand
    are read by the same code, or the fixtures have been proving something else."""
    code = main(["gather", "--facts", str(COLLECTED)])

    printed = capsys.readouterr().out
    assert code == EXIT_OK
    assert "gather-debian12" in printed
    assert "Debian 12" in printed


def test_a_collected_host_carries_what_the_gates_read() -> None:
    """Not that the file parses -- that it answers the questions the rules ask. A collector
    that produced a valid document missing the facts every rule reads would pass a schema
    and be useless."""
    collected = json.loads(COLLECTED.read_text(encoding="utf-8"))

    assert collected["os"]["family"] == "debian"
    assert collected["services"], "an empty service list is what makes a conflict rule pass"
    assert collected["privileges"]["can_escalate"] is True
    assert collected["network"]["listening_ports"] == []
    assert "reachable_repositories" not in collected


def test_a_summary_of_a_real_machine_stays_a_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A hundred and nine service names is forty lines that only a profile could
    interpret. The names are in the document; the rule that reads them is in preflight."""
    main(["gather", "--facts", str(COLLECTED)])

    printed = capsys.readouterr().out
    assert "109 services" in printed
    assert "systemd-journald" not in printed
    for line in printed.splitlines():
        assert len(line) <= 88, "a summary nobody can read in a task log is not a summary"


def test_a_short_list_is_still_spelled_out(capsys: pytest.CaptureFixture[str]) -> None:
    """What decides is how much fits on a line, which is a fact about the page rather than
    a judgement about the host."""
    main(["gather", "--facts", str(HOSTS / "crowded.json")])
    assert "1 service: exampledb" in capsys.readouterr().out
