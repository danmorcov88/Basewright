"""The gather verb: the first one that does something.

It reads a facts document, normalizes it and says what the machine is. Collecting those
facts from a live host runs over SSH, which is Ansible's half of the split and belongs to
Phase A -- so the verb says that plainly rather than implying a machine was contacted.
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
