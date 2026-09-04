"""The CLI is a thin shell: it should parse, dispatch, and nothing more."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureFixture

from basewright import __version__
from basewright.cli import VERBS, build_parser, main


def test_version_is_reported() -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["--version"])
    assert exit_info.value.code == 0


def test_a_verb_is_required() -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args([])
    assert exit_info.value.code != 0


@pytest.mark.parametrize("verb", sorted(VERBS))
def test_every_verb_parses(verb: str) -> None:
    assert build_parser().parse_args([verb]).verb == verb


def test_apply_is_not_a_verb_of_this_cli() -> None:
    """Applying is Ansible's job. The split is the architecture, not an omission."""
    assert "apply" not in VERBS


#: The verbs that are still a promise. Each one exits 69 and points at the status page,
#: so an unbuilt verb is a fact a reader can check rather than a thing that hangs.
UNBUILT = ("verify",)


@pytest.mark.parametrize("verb", UNBUILT)
def test_unbuilt_verbs_exit_predictably(verb: str) -> None:
    assert main([verb]) == 69


def test_the_list_of_unbuilt_verbs_is_kept_honest() -> None:
    """A verb that starts working and stays on this list makes the test above vacuous."""
    assert set(UNBUILT) < set(VERBS)
    assert "gather" not in UNBUILT
    assert "preflight" not in UNBUILT
    assert "plan" not in UNBUILT


def test_version_string_is_set() -> None:
    assert __version__


# ---------------------------------------------------------------------------- preflight

ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "test" / "fixtures" / "hosts"
PROFILE = ROOT / "test" / "fixtures" / "profiles" / "exampledb"


def preflight(*extra: str) -> list[str]:
    return ["preflight", "--facts", str(FACTS / "typical.json"), "--profile", str(PROFILE), *extra]


def test_preflight_passes_a_host_that_can_be_provisioned(capsys: CaptureFixture[str]) -> None:
    assert main(preflight()) == 0
    assert "PASSED" in capsys.readouterr().out


def test_preflight_refuses_a_host_that_cannot(capsys: CaptureFixture[str]) -> None:
    """Exit 2 is the reportable refusal, not an error: the tool worked and said no."""
    arguments = ["preflight", "--facts", str(FACTS / "crowded.json"), "--profile", str(PROFILE)]
    assert main(arguments) == 2
    assert "REFUSED" in capsys.readouterr().err


def test_a_refusal_goes_to_standard_error_and_a_pass_does_not(
    capsys: CaptureFixture[str],
) -> None:
    """So a pipeline capturing a passing report is never handed a refusal instead."""
    arguments = ["preflight", "--facts", str(FACTS / "crowded.json"), "--profile", str(PROFILE)]
    main(arguments)
    refused = capsys.readouterr()
    assert refused.out == ""
    assert "REFUSED" in refused.err

    main(preflight())
    passed = capsys.readouterr()
    assert "PASSED" in passed.out
    assert passed.err == ""


def test_preflight_writes_the_document_when_asked(capsys: CaptureFixture[str]) -> None:
    assert main([*preflight(), "--json"]) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["schema_version"] == "1"
    assert written["request"]["engine"] == "exampledb"
    assert written["results"]


def test_preflight_needs_both_facts_and_a_profile(capsys: CaptureFixture[str]) -> None:
    assert main(["preflight", "--facts", str(FACTS / "typical.json")]) == 64
    assert main(["preflight", "--profile", str(PROFILE)]) == 64
    assert "required" in capsys.readouterr().err


def test_preflight_refuses_a_version_the_profile_does_not_support(
    capsys: CaptureFixture[str],
) -> None:
    assert main([*preflight(), "--engine-version", "9"]) == 2
    assert "not a version this profile supports" in capsys.readouterr().err


def test_preflight_takes_the_request_from_the_command_line(capsys: CaptureFixture[str]) -> None:
    main([*preflight(), "--instance", "reporting", "--port", "6433", "--json"])
    written = json.loads(capsys.readouterr().out)
    assert written["request"]["instance"] == "reporting"
    assert written["request"]["port"] == 6433


def test_preflight_defaults_the_host_to_the_one_the_facts_describe(
    capsys: CaptureFixture[str],
) -> None:
    main([*preflight(), "--json"])
    written = json.loads(capsys.readouterr().out)
    assert written["request"]["host"] == "db-typical.invalid"


def test_preflight_refuses_facts_that_describe_another_machine(
    capsys: CaptureFixture[str],
) -> None:
    assert main([*preflight(), "--host", "db-elsewhere.invalid"]) == 2
    assert "host.reachable" in capsys.readouterr().err


def test_preflight_refuses_a_profile_that_does_not_hold_together(
    capsys: CaptureFixture[str],
) -> None:
    broken = ROOT / "test" / "fixtures" / "profiles" / "malformed"
    arguments = ["preflight", "--facts", str(FACTS / "typical.json"), "--profile", str(broken)]
    assert main(arguments) == 2
    assert "is not a valid profile" in capsys.readouterr().err


def test_preflight_reports_a_missing_profile_as_usage(capsys: CaptureFixture[str]) -> None:
    arguments = ["preflight", "--facts", str(FACTS / "typical.json"), "--profile", "nowhere"]
    assert main(arguments) == 64
    assert "not a profile directory" in capsys.readouterr().err


def test_preflight_reports_missing_facts_as_usage(capsys: CaptureFixture[str]) -> None:
    arguments = ["preflight", "--facts", "nowhere.json", "--profile", str(PROFILE)]
    assert main(arguments) == 64
    capsys.readouterr()


# --------------------------------------------------------- reading a plan back again


ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PLAN = ROOT / "test" / "golden" / "plan" / "typical.json"
EDITED_PLAN = ROOT / "test" / "fixtures" / "plan" / "edited.json"


def test_a_plan_can_be_read_back_and_rendered(capsys: pytest.CaptureFixture[str]) -> None:
    """A plan a second person cannot read is not reviewable by a second person, which is
    the separation the artifact exists for."""
    code = main(["plan", "--from", str(GOLDEN_PLAN)])

    printed = capsys.readouterr().out
    assert code == 0
    assert "BASEWRIGHT PLAN" in printed
    assert "d6cb9a5adc52" in printed


def test_a_plan_that_has_been_edited_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    """The id is a digest of the plan's own content, so it is a checksum as well as a
    name, and this is the thing that checks it."""
    code = main(["plan", "--from", str(EDITED_PLAN)])

    refusal = capsys.readouterr().err
    assert code == 2
    assert "calls itself" in refusal
    assert "edited since it was produced" in refusal


def test_a_file_that_is_not_a_plan_is_refused_against_the_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = tmp_path / "not-a-plan.json"
    document.write_text('{"schema_version": "1"}', encoding="utf-8")

    code = main(["plan", "--from", str(document)])

    assert code == 2
    assert "is required but missing" in capsys.readouterr().err


def test_a_file_that_is_not_json_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = tmp_path / "broken.json"
    document.write_text("{", encoding="utf-8")

    code = main(["plan", "--from", str(document)])

    assert code == 2
    assert "not readable JSON" in capsys.readouterr().err


def test_a_missing_file_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["plan", "--from", "nowhere.json"])

    assert code == 64
    assert "cannot read" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra",
    [
        ["--json"],
        ["--facts", str(ROOT / "test" / "fixtures" / "hosts" / "typical.json")],
        ["--profile", str(ROOT / "test" / "fixtures" / "profiles" / "exampledb")],
    ],
    ids=["json", "facts", "profile"],
)
def test_reading_a_plan_and_producing_one_are_different_jobs(
    extra: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["plan", "--from", str(GOLDEN_PLAN), *extra])

    assert code == 64
    assert "cannot be combined with" in capsys.readouterr().err


def test_every_refusal_wraps_to_a_width_a_terminal_can_show(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["plan", "--from", str(EDITED_PLAN)])

    for line in capsys.readouterr().err.splitlines():
        assert len(line) <= 88
