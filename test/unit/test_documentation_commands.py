"""The commands the README shows are the commands that produced its pictures.

A terminal image in this repository is real output, and `--check` in CI keeps it that way.
That leaves one gap the images cannot close on their own: the text a reader copies is not
inside the image, so it can drift from the command that made it. A README that tells you to
run one thing and shows you the output of another is worse than one with no commands in it,
because it looks checked.

So each capture's command is written above the picture it produced, as copy-pasteable text,
and this holds the two together.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"

sys.path.insert(0, str(ROOT / "tools"))

from render_assets import CAPTURES  # noqa: E402

#: A fenced block holding exactly one line. The multi-line blocks are lists of targets
#: rather than a command with an answer, and no picture claims to be their output.
SINGLE_LINE_FENCE = re.compile(r"^```\n(.+)\n```$", re.MULTILINE)


def readme() -> str:
    return README.read_text(encoding="utf-8")


def fenced_commands() -> list[str]:
    return SINGLE_LINE_FENCE.findall(readme())


def shown_captures() -> list[str]:
    """The captures the README actually displays. It does not have to show all of them."""
    text = readme()
    return [entry.name for entry in CAPTURES if f"docs/assets/{entry.name}-light.svg" in text]


def test_the_readme_shows_captures_at_all() -> None:
    """A check over an empty list is a check that always passes."""
    assert shown_captures()


def test_every_picture_carries_the_command_that_produced_it() -> None:
    shown = set(shown_captures())
    commands = fenced_commands()
    missing = [
        entry.prompt for entry in CAPTURES if entry.name in shown and entry.prompt not in commands
    ]
    assert not missing, f"shown in the README with no copy-pasteable command: {missing}"


def test_no_command_in_the_readme_is_a_near_miss_of_a_real_one() -> None:
    """The failure this exists for is a flag that changed in the renderer and not here.

    A command a reader can copy is checked against the capture it resembles rather than
    against the whole set, so that an example naming something which does not exist yet --
    a profile, in `profiles/` -- is still allowed to be written as a placeholder.
    """
    prompts = {entry.prompt for entry in CAPTURES}
    for command in fenced_commands():
        if not command.startswith(("basewright ", "python -m basewright.")) or "<" in command:
            continue
        assert command in prompts, (
            f"the README says to run `{command}`, which is not a command any picture in it "
            "was produced by. Either capture it, or write it as a placeholder."
        )


#: A playbook is the entry point for anything that reaches a machine (ADR-0020), so the
#: README names one. It cannot be captured -- there is no host in CI to point it at -- but
#: the path it names can be checked, which is the half of the claim that can go stale.
PLAYBOOK = re.compile(r"^ansible-playbook\s+(\S+)", re.MULTILINE)


def test_every_playbook_the_readme_tells_you_to_run_exists() -> None:
    named = PLAYBOOK.findall(readme())
    assert named, "the README names no playbook, though a playbook is how a verb is run"
    missing = [path for path in named if not (ROOT / path).is_file()]
    assert not missing, f"the README points at playbooks that do not exist: {missing}"
