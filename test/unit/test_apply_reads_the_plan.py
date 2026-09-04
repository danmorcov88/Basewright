"""Apply consumes plan.json and nothing else, asserted against the tasks rather than hoped.

This is the constraint the whole arrangement rests on: the document somebody approved is
the document that runs. It is also the easiest one to break by accident, because reaching
into the profile for one more value is always the smaller change than fixing the plan --
and each time it happens the plan describes a little less of what will happen.

There is exactly one thing apply looks up outside the plan, and it is a file the plan names
by name rather than a value (ADR-0022). That exception is written down here, so a second
one has to be argued for rather than added.

The other invariant guarded here is that a task handling a generated password is silent.
Ansible logs its own arguments by default, so a secret leaks not because somebody printed
one but because nobody said not to.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLES = ROOT / "ansible" / "roles"
PLAYBOOK = ROOT / "ansible" / "playbooks" / "apply.yml"

#: The roles apply enters. `common` is the shared half; the other is an engine's own, and
#: it is named here because this file is about what apply does rather than about the core.
APPLYING_ROLES: tuple[str, ...] = ("common", "postgresql")

#: The one filter that reaches outside the plan, and the whole of the exception. It resolves
#: a template by the name the plan gives it; every value poured into that template comes
#: from the plan.
LOOKS_OUTSIDE: str = "basewright_template"


def task_files() -> list[Path]:
    found: list[Path] = []
    for role in APPLYING_ROLES:
        found.extend(sorted((ROLES / role / "tasks").glob("*.yml")))
    return found


def tasks_in(path: Path) -> list[dict[str, Any]]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, list) else []


#: How the playbook names the engine's role. It is a template rather than a name, which is
#: the point: the plan says which engine, and the playbook is a shared file that must never
#: have learned one.
FROM_THE_PLAN = "{{ basewright_plan.profile.engine }}"

#: The engine role this repository ships, used only to resolve the template above so the
#: phases can be checked against files that exist.
ENGINE = "postgresql"


def phases_of(playbook: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Every phase the playbook runs, as the role it enters and the file it enters at."""
    found = []
    for task in playbook[0].get("tasks", []):
        include = task.get("ansible.builtin.include_role")
        if include is None:
            continue
        found.append((include["name"], include.get("tasks_from", "main")))
    return found


@pytest.fixture(scope="module")
def playbook() -> list[dict[str, Any]]:
    loaded = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    return loaded


def test_there_are_tasks_to_check() -> None:
    """A guard that scans nothing is a guard that always passes."""
    assert task_files()
    assert len(task_files()) > 4


# ------------------------------------------------------------------ nothing but the plan


@pytest.mark.parametrize(
    "path", task_files(), ids=lambda path: f"{path.parent.parent.name}/{path.name}"
)
def test_no_task_goes_looking_for_a_profile(path: Path) -> None:
    """The plan is the input. A role that read the profile would be deciding again, at the
    one moment when the decisions have already been reviewed and approved."""
    body = path.read_text(encoding="utf-8")

    assert "profiles/" not in body, f"{path.name} reaches into the profile directory"
    assert "--profile" not in body, f"{path.name} passes a profile to something"
    assert "--engine" not in body, f"{path.name} looks an engine up rather than reading one"


@pytest.mark.parametrize(
    "path", task_files(), ids=lambda path: f"{path.parent.parent.name}/{path.name}"
)
def test_the_only_thing_looked_up_outside_the_plan_is_a_template(path: Path) -> None:
    """One exception, and it is a file rather than a value: `basewright_template` resolves
    a template by the name the plan gives it, and every value poured into it comes from the
    plan. A second name reaching outside would be an exception nobody argued for."""
    reaching = set(re.findall(r"basewright_[a-z_.]*", path.read_text(encoding="utf-8")))
    outside = {
        name
        for name in reaching
        if not name.startswith("basewright_plan") and name != LOOKS_OUTSIDE
    }

    assert not outside, f"{path.name} reads {sorted(outside)}, which the plan does not carry"


def test_the_playbook_takes_one_input_and_it_is_a_plan(playbook: list[dict[str, Any]]) -> None:
    play = playbook[0]

    assert "basewright_plan_file" in yaml.safe_dump(play["vars"])
    assert "mandatory" in yaml.safe_dump(play["vars"]), (
        "a missing plan has to fail where the mistake was made, not four tasks later"
    )


# ------------------------------------------------------------------------- the phases


def test_every_phase_the_playbook_runs_exists(playbook: list[dict[str, Any]]) -> None:
    """A phase named and not written is a role that fails halfway through an apply."""
    for role, phase in phases_of(playbook):
        named = ENGINE if role == FROM_THE_PLAN else role
        assert (ROLES / named / "tasks" / f"{phase}.yml").is_file(), f"{named} has no {phase}"


def test_the_engine_is_read_from_the_plan_rather_than_named(
    playbook: list[dict[str, Any]],
) -> None:
    """The document says which engine, and the document is what a person approved. A
    playbook that named one would be a shared file that had learned an engine."""
    engines = {role for role, _ in phases_of(playbook) if role != "common"}

    assert engines == {FROM_THE_PLAN}


def test_the_shared_phases_fall_between_the_engine_phases(
    playbook: list[dict[str, Any]],
) -> None:
    """The order is the order the plan lists its own changes in, which is why the roles
    interleave rather than running one after the other. A profile whose vendor package
    makes the service account cannot have its directories owned before the packages are
    installed -- which is how this was found, on a real container."""
    entered = [role for role, _ in phases_of(playbook)]

    assert entered.index("common") > 0, "packages come before the account and the directories"
    assert entered != sorted(set(entered), key=entered.index) * 1 or len(set(entered)) == 1
    assert entered.count("common") >= 2, "the shared phases are not one block"


def test_every_phase_the_engine_role_has_is_one_the_playbook_runs(
    playbook: list[dict[str, Any]],
) -> None:
    """Except the ones another phase includes. A task file nothing reaches is dead."""
    named = {phase for _, phase in phases_of(playbook)}
    included = {
        Path(str(task["ansible.builtin.include_tasks"])).stem
        for path in task_files()
        for task in tasks_in(path)
        if "ansible.builtin.include_tasks" in task
    }
    included |= {
        task["ansible.builtin.include_role"].get("tasks_from", "main")
        for path in task_files()
        for task in tasks_in(path)
        if "ansible.builtin.include_role" in task
    }

    for path in task_files():
        assert path.stem in named | included, f"{path} is reached by nothing"


# ------------------------------------------------------------------------- secrets


def test_every_task_that_handles_a_password_is_silent() -> None:
    """Ansible logs its own arguments, so a secret leaks not because somebody printed one
    but because nobody said not to. This is the assertion that keeps ADR-0007 true in the
    half of the project written in YAML."""
    handled = 0
    for path in task_files():
        for task in tasks_in(path):
            if "secret_value" not in yaml.safe_dump(task):
                continue
            handled += 1
            assert task.get("no_log") is True, f"{task.get('name')!r} in {path.name} is not silent"

    assert handled, "nothing was checked, which means this guard is scanning the wrong thing"


def test_no_secret_ever_reaches_a_command_line() -> None:
    """A password in argv is readable by every process on the host through `ps`, and it
    lands in shell history besides. It goes in over stdin or it does not go."""
    for path in task_files():
        for task in tasks_in(path):
            command = task.get("ansible.builtin.command")
            if not isinstance(command, dict):
                continue
            argv = yaml.safe_dump(command.get("argv", []))
            assert "secret_value" not in argv, f"{task.get('name')!r} puts a secret in argv"


def test_the_store_is_a_seam_rather_than_a_detail() -> None:
    """Semaphore's store is the real target and a container needs one anyway, so the sink
    is named. A second implementation is a file beside the first, not an edit to everything
    that calls it."""
    defaults = yaml.safe_load((ROLES / "common" / "defaults" / "main.yml").read_text("utf-8"))

    assert defaults["common_secret_store"] in defaults["common_secret_stores"]
