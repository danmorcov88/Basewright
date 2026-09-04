"""The collecting role must not be able to change the host it is reading.

`gather` is the one verb an operator is expected to run against a machine nobody has
agreed to touch yet -- before the gates, before a plan exists, before anybody has approved
anything. It is only worth having if that is true, and "it is read-only" is the kind of
claim that stays true right up until somebody adds a task that seemed harmless.

Molecule's idempotence check is the usual way this gets caught, and it cannot be used here:
the document records the moment it was collected, so a second run writes a different file,
and a collector that produced byte-identical output would be lying about when it looked.
Rather than lose the guarantee, it is asserted against the tasks themselves, which is the
stronger of the two anyway -- a property of the role rather than of one run of it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible" / "roles" / "gather"
TASKS = ROLE / "tasks" / "main.yml"

#: Modules that cannot alter the machine they run against, and why each is here.
#:
#: The list is short on purpose. Anything not on it has to be argued for in a pull request,
#: which is the point: the failure this guards against is a task that looked harmless to
#: whoever added it.
READ_ONLY: dict[str, str] = {
    "ansible.builtin.service_facts": "enumerates units",
    "ansible.builtin.setup": "reads facts",
    "ansible.builtin.slurp": "reads a file",
    "ansible.builtin.command": "runs something, and is checked separately below",
    "ansible.builtin.assert": "refuses, and refusing is not changing",
    "ansible.builtin.uri": "makes a request, and the method is checked separately below",
    "ansible.builtin.set_fact": "arranges what was already read",
    "ansible.builtin.debug": "prints",
}

#: Commands whose whole purpose is to report. Each is here because it was needed, and a
#: command not on this list is a command somebody has to justify in review -- which is
#: cheaper than reading every shell line in a diff and hoping to spot the one that writes.
REPORTING_COMMANDS: tuple[str, ...] = (
    "ss ",
    "locale -a",
    "timedatectl show",
    "ufw status",
    "id -u",
)


def tasks() -> list[dict[str, Any]]:
    loaded = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    assert isinstance(loaded, list), f"{TASKS} does not contain a task list"
    return loaded


def against_the_target(task: dict[str, Any]) -> bool:
    """Tasks delegated to the control node run where the document is written, not on the
    host being read, so the rule under test does not apply to them."""
    return task.get("delegate_to") != "localhost"


def module_of(task: dict[str, Any]) -> str:
    keys = [key for key in task if key.startswith("ansible.")]
    assert len(keys) == 1, f"cannot tell which module {task.get('name')!r} uses"
    return keys[0]


def test_the_role_has_tasks_to_check() -> None:
    """A guard that scans nothing is a guard that always passes."""
    assert tasks()


def test_nothing_that_touches_the_host_can_change_it() -> None:
    used = {module_of(task) for task in tasks() if against_the_target(task)}
    assert used <= set(READ_ONLY), f"not known to be read-only: {sorted(used - set(READ_ONLY))}"


def test_every_command_says_it_changed_nothing() -> None:
    """Ansible assumes a command changed something, which is the right default and the
    wrong answer here. A command without this reports a change on every run, and a role
    that reports changes nobody can explain is a role nobody believes is read-only."""
    for task in tasks():
        if module_of(task) != "ansible.builtin.command":
            continue
        assert task.get("changed_when") is False, f"{task['name']!r} does not declare it reads"


def test_every_command_is_one_that_reports_rather_than_acts() -> None:
    for task in tasks():
        if module_of(task) != "ansible.builtin.command" or not against_the_target(task):
            continue
        invocation = str(task["ansible.builtin.command"]).strip()
        assert invocation.startswith(REPORTING_COMMANDS), f"unrecognised command: {invocation!r}"


#: The request methods that ask a server something without telling it anything. A module
#: that can POST is not read-only because it is on a list, so the list is not where the
#: guarantee lives -- the method is.
READING_METHODS: tuple[str, ...] = ("GET", "HEAD")


def test_every_request_only_reads() -> None:
    """`uri` is on the read-only list because of how it is called, not because of what it
    is. It will happily PUT, and a probe that asked a repository to accept something would
    be a collector writing to a third party on the way past."""
    for task in tasks():
        if module_of(task) != "ansible.builtin.uri":
            continue
        method = str(task["ansible.builtin.uri"].get("method", "GET")).upper()
        assert method in READING_METHODS, f"{task['name']!r} uses {method}"


def test_a_request_that_did_not_answer_is_an_answer() -> None:
    """A repository that cannot be reached is the outcome a blocking rule exists to
    receive. A probe that failed the task would end the run before the document carrying
    that outcome was written, which is the one result nobody could act on."""
    for task in tasks():
        if module_of(task) != "ansible.builtin.uri":
            continue
        assert task.get("failed_when") is False, f"{task['name']!r} would fail the run"


@pytest.mark.parametrize("directory", ["handlers", "files"])
def test_the_role_carries_nothing_it_would_put_on_a_host(directory: str) -> None:
    """A handler exists to act on a change, and a collector has no changes to act on. A
    file exists to be copied somewhere, and this role copies nothing to a target."""
    assert not (ROLE / directory).exists()
