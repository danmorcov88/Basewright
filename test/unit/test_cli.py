"""The CLI is a thin shell: it should parse, dispatch, and nothing more."""

from __future__ import annotations

import ast
import json
import re
import shutil
from pathlib import Path

import pytest
from _pytest.capture import CaptureFixture

from basewright import __version__, cli
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


# ------------------------------------------------------------------- producing a plan


def plan_arguments(host: str = "typical", *extra: str) -> list[str]:
    return ["plan", "--facts", str(FACTS / f"{host}.json"), "--profile", str(PROFILE), *extra]


def test_plan_renders_the_artifact_for_a_host_that_passes(capsys: CaptureFixture[str]) -> None:
    assert main(plan_arguments()) == 0
    assert "BASEWRIGHT PLAN" in capsys.readouterr().out


def test_plan_writes_the_artifact_when_asked(capsys: CaptureFixture[str]) -> None:
    """--json is what apply reads, so it has to be the document and nothing else."""
    assert main(plan_arguments("typical", "--json")) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["schema_version"] == "1"
    assert written["plan_id"]


def test_a_blocked_host_produces_a_refusal_and_no_plan(capsys: CaptureFixture[str]) -> None:
    """There is no partial plan and no flag that produces one."""
    assert main(plan_arguments("crowded")) == 2
    refused = capsys.readouterr()
    assert refused.out == ""
    assert "REFUSED" in refused.err
    assert "BASEWRIGHT PLAN" not in refused.err


def test_plan_refuses_a_version_the_profile_does_not_support(capsys: CaptureFixture[str]) -> None:
    assert main(plan_arguments("typical", "--engine-version", "9")) == 2
    assert "not a version this profile supports" in capsys.readouterr().err


def test_plan_needs_both_facts_and_a_profile(capsys: CaptureFixture[str]) -> None:
    assert main(["plan", "--facts", str(FACTS / "typical.json")]) == 64
    assert "required" in capsys.readouterr().err


def test_gather_needs_facts_and_says_why_it_cannot_collect_them(
    capsys: CaptureFixture[str],
) -> None:
    assert main(["gather"]) == 64
    refusal = capsys.readouterr().err
    assert "--facts is required" in refusal
    assert "not built yet" in refusal


def test_gather_refuses_facts_that_do_not_hold_up(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    document = tmp_path / "facts.json"
    document.write_text('{"schema_version": "1"}', encoding="utf-8")
    assert main(["gather", "--facts", str(document)]) == 2
    assert "is required but missing" in capsys.readouterr().err


def test_gather_writes_the_document_when_asked(capsys: CaptureFixture[str]) -> None:
    assert main(["gather", "--facts", str(FACTS / "typical.json"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["os"]["family"] == "debian"


@pytest.mark.parametrize(
    "arguments",
    [
        ["gather"],
        ["plan", "--facts", str(FACTS / "typical.json")],
        ["preflight", "--profile", str(PROFILE)],
    ],
    ids=["gather", "plan", "preflight"],
)
def test_every_usage_refusal_wraps_the_way_every_report_does(
    arguments: list[str], capsys: CaptureFixture[str]
) -> None:
    """A refusal is read in a terminal, in a task log and in a documentation image, and
    none of the three wraps kindly on its own."""
    main(arguments)
    printed = capsys.readouterr().err.splitlines()
    assert printed
    for line in printed:
        assert len(line) <= 88


# --------------------------------------------------------- the exit codes, as a set

README = ROOT / "README.md"

#: Every code, and one real invocation that produces it. Written out rather than derived,
#: because a code nobody can reach from the command line is a code that does not exist,
#: and only a real run proves otherwise.
REACHABLE: tuple[tuple[int, list[str]], ...] = (
    (0, ["plan", "--from", str(GOLDEN_PLAN)]),
    (2, ["preflight", "--facts", str(FACTS / "crowded.json"), "--profile", str(PROFILE)]),
    (64, ["plan", "--from", "nowhere.json"]),
    (69, ["verify"]),
)


def test_the_exit_codes_are_a_closed_set() -> None:
    """The constants and the registry are two views of one contract (ADR-0019)."""
    constants = {
        value
        for name, value in vars(cli).items()
        if name.startswith("EXIT_") and isinstance(value, int)
    }
    assert constants == {entry.code for entry in cli.EXIT_CODES}


@pytest.mark.parametrize("code,arguments", REACHABLE, ids=lambda value: str(value)[:12])
def test_every_documented_code_is_reachable(
    code: int, arguments: list[str], capsys: CaptureFixture[str]
) -> None:
    assert main(arguments) == code
    capsys.readouterr()


def test_every_documented_code_is_covered_by_a_real_invocation() -> None:
    """So that a code added to the registry cannot sit there unexercised."""
    assert {code for code, _ in REACHABLE} == {entry.code for entry in cli.EXIT_CODES}


def test_the_cli_returns_no_code_it_has_not_documented() -> None:
    """A bare `return 2` would satisfy every test above and still be outside the set.

    The registry is only a contract while every exit runs through a named constant, so
    this reads the source and insists on it.
    """
    tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    literals = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, int)
    ]
    assert not literals, f"cli.py returns an integer literal at lines {literals}"


def test_the_readme_table_says_what_the_registry_says() -> None:
    """The table an operator reads is the set the tool returns, or it is fiction."""
    table = re.compile(r"^\| `(\d+)` \| (.+?) \| (.+?) \|$", re.MULTILINE)
    rows = table.findall(README.read_text(encoding="utf-8"))
    documented = [(int(code), meaning, response) for code, meaning, response in rows]
    assert documented == [(e.code, e.meaning, e.response) for e in cli.EXIT_CODES]


# ------------------------------------------------------- what a verb declares it reads


def test_an_unbuilt_verb_declares_no_inputs() -> None:
    """A flag no implementation will ever read is a promise --help cannot keep."""
    for verb in cli.UNBUILT:
        with pytest.raises(SystemExit):
            build_parser().parse_args([verb, "--facts", "anything.json"])


def test_the_verbs_that_are_built_all_read_facts() -> None:
    """The other half of the check above: the flag is absent because verify never reads
    a facts document, not because nothing does."""
    for verb in set(VERBS) - set(cli.UNBUILT):
        assert build_parser().parse_args([verb, "--facts", "anything.json"]).facts


def test_only_the_verbs_that_take_a_request_take_a_profile() -> None:
    assert build_parser().parse_args(["plan", "--profile", "somewhere"]).profile
    assert build_parser().parse_args(["preflight", "--profile", "somewhere"]).profile
    with pytest.raises(SystemExit):
        build_parser().parse_args(["gather", "--profile", "somewhere"])


# ------------------------------------------- a profile that loads and then does not work


def broken_profile(tmp_path: Path, filename: str, misspelling: str) -> Path:
    """A copy of the fixture profile with one expression made unreadable.

    These are the failures a schema cannot catch. A profile whose files all validate can
    still name a fact nothing reports, and the CLI's job at that point is to refuse with
    the same exit code as any other refusal rather than to hand an operator a traceback.
    """
    directory = tmp_path / "broken"
    shutil.copytree(PROFILE, directory)
    document = directory / filename
    document.write_text(
        document.read_text(encoding="utf-8").replace("host.memory.total_bytes", misspelling, 1),
        encoding="utf-8",
    )
    return directory


def test_a_rule_that_cannot_be_evaluated_is_refused_not_raised(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    directory = broken_profile(tmp_path, "requirements.yml", "host.memroy.total_bytes")
    arguments = ["--facts", str(FACTS / "typical.json"), "--profile", str(directory)]

    assert main(["preflight", *arguments]) == 2
    assert "not something this reads" in capsys.readouterr().err
    assert main(["plan", *arguments]) == 2
    assert "not something this reads" in capsys.readouterr().err


def test_a_sizing_rule_that_reads_an_unreported_fact_produces_no_plan(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    """Not a defect in the profile and not a host that fell short: nobody can tell, so
    there is no value to write down and no plan."""
    directory = broken_profile(tmp_path, "sizing.yml", "host.memroy.total_bytes")
    arguments = ["plan", "--facts", str(FACTS / "typical.json"), "--profile", str(directory)]

    assert main(arguments) == 2
    refused = capsys.readouterr()
    assert refused.out == ""
    assert "host.memroy.total_bytes" in refused.err


def test_facts_that_do_not_hold_up_are_refused_by_every_verb_that_reads_them(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    document = tmp_path / "facts.json"
    document.write_text('{"schema_version": "1"}', encoding="utf-8")
    arguments = ["--facts", str(document), "--profile", str(PROFILE)]

    assert main(["preflight", *arguments]) == 2
    assert "is required but missing" in capsys.readouterr().err
    assert main(["plan", *arguments]) == 2
    assert "is required but missing" in capsys.readouterr().err
