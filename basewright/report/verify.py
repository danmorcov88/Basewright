"""What a verify run says for itself.

The reader is somebody who has just been told an instance is not what its plan says, and
what they need is which check, what was read back, what was promised, and what to do. This
puts those four next to each other, in that order, for everything that did not pass.

Unlike a preflight report, this one prints the passes too. A preflight is read while
deciding whether to change a machine, so naming eighteen agreements would bury the two
lines somebody has to act on. A verify report is the record that an instance was proved --
it is what gets attached to a change request and read again months later -- and a record
that lists only the failures cannot be told apart from a record of a run that asked very
little.

ASCII only, for the same reason every other report here is: it is read in a terminal, in a
task log, and in a documentation image generated on a machine that may not agree with this
one about the console encoding.
"""

from __future__ import annotations

from collections.abc import Sequence

from basewright.report.problems import REPORT_WIDTH, wrapped
from basewright.verify.model import Outcome
from basewright.verify.run import CheckResult, VerifyResult

#: Width of the identifier column, clamped so one long check id cannot push every observed
#: value off the right-hand edge.
_IDENTIFIER_WIDTH = (24, 30)

#: What each outcome is labelled, padded to one width so the labels read down as a column.
_LABEL: dict[Outcome, str] = {
    Outcome.FAIL: "FAIL ",
    Outcome.UNOBSERVED: "?    ",
    Outcome.PASS: "PASS ",
}

#: The marker on what the plan promised, and on what to do about it.
_EXPECTED = "planned: "
_REMEDY = "-> "

#: Hanging indent of the verdict, under the word that labels it.
_VERDICT_INDENT = 11


def render_verify(result: VerifyResult) -> str:
    """The whole rendering: what was verified, every check, and the verdict."""
    lines = [
        f"VERIFY  {result.host} -- {result.engine} {result.version}, instance {result.instance}",
        f"  plan {result.plan_id}, read {result.observed_at:%Y-%m-%dT%H:%M:%SZ}",
        f"  {_counts(result)}",
    ]

    # A blank line wherever a check runs to more than one line, and none between checks
    # that each say what they found on the line they are named on. Eleven passing checks
    # read as a list somebody can run their eye down; the same eleven separated by blank
    # lines read as eleven separate announcements.
    width = _column_width(result.results)
    folded = False
    for entry in result.results:
        rendered = _result(entry, width)
        if folded or len(rendered) > 1:
            lines.append("")
        lines.extend(rendered)
        folded = len(rendered) > 1

    lines.append("")
    lines.extend(_verdict(result))
    return "\n".join(lines)


def _counts(result: VerifyResult) -> str:
    """The summary line, in the order the outcomes matter."""
    summary = result.summary
    return (
        f"{summary['pass']} pass -- {summary['fail']} fail -- {summary['unobserved']} not observed"
    )


def _result(entry: CheckResult, width: int) -> list[str]:
    """One check: what it read, what was promised, and what to do about the difference.

    What was promised is printed only when it differs from what was read, because on a
    passing check the two say the same thing twice and the report is long enough already.
    """
    label = _LABEL[entry.outcome]
    margin = 2 + len(label) + 1 + width + 2
    indent = " " * margin

    observed = wrapped(entry.observed, width=REPORT_WIDTH - margin) or [""]
    if len(entry.identifier) > width:
        # An identifier wider than its column takes a line of its own rather than pushing
        # that one result out of alignment with every other one.
        lines = [f"  {label} {entry.identifier}", f"{indent}{observed[0]}"]
    else:
        lines = [f"  {label} {entry.identifier.ljust(width)}  {observed[0]}"]
    lines.extend(f"{indent}{line}" for line in observed[1:])

    if entry.outcome is not Outcome.PASS and entry.expected:
        lines.extend(_marked(entry.expected, _EXPECTED, indent, margin))
    if entry.outcome is not Outcome.PASS and entry.remediation:
        lines.extend(_marked(entry.remediation, _REMEDY, indent, margin))
    return lines


def _marked(text: str, marker: str, indent: str, margin: int) -> list[str]:
    """A marked continuation line, wrapped under its own marker."""
    folded = wrapped(text, width=REPORT_WIDTH - margin - len(marker))
    continued = " " * len(marker)
    return [
        f"{indent}{marker if index == 0 else continued}{line}" for index, line in enumerate(folded)
    ]


def _verdict(result: VerifyResult) -> list[str]:
    """The one line somebody reads first, and sometimes the only one they read.

    Three endings, because there are three things that can have happened. Everything
    passed. Something did not match, which says the instance is not what the plan
    describes. Or everything that ran passed and something did not run, which says nothing
    about the instance at all -- and saying that plainly is the whole point of keeping the
    third outcome (ADR-0025).
    """
    failed = result.counting(Outcome.FAIL)
    unobserved = result.counting(Outcome.UNOBSERVED)

    if failed:
        checks = "check" if failed == 1 else "checks"
        also = f" A further {unobserved} could not be observed at all." if unobserved else ""
        return _hanging(
            "FAILED",
            f"{failed} {checks} did not match the plan. This instance is not what "
            f"{result.plan_id} describes, and the artifact that says it is has been wrong "
            f"since something changed.{also}",
        )
    if unobserved:
        checks = "check" if unobserved == 1 else "checks"
        return _hanging(
            "UNPROVED",
            f"nothing contradicts the plan, and {unobserved} {checks} could not be put to "
            f"this instance at all. Nothing was proved about them, which is not the same "
            f"as their having passed, so this run does not verify the instance.",
        )
    total = len(result.results)
    return _hanging(
        "VERIFIED",
        f"all {total} checks match {result.plan_id}. This instance is what the plan says it is.",
    )


def _hanging(label: str, text: str) -> list[str]:
    """A labelled verdict, wrapped under itself rather than off the edge."""
    indent = " " * _VERDICT_INDENT
    lines = wrapped(text, width=REPORT_WIDTH - _VERDICT_INDENT)
    head = f"{label.ljust(_VERDICT_INDENT)}{lines[0]}"
    return [head, *(f"{indent}{line}" for line in lines[1:])]


def _column_width(results: Sequence[CheckResult]) -> int:
    """Width of the identifier column: the longest identifier, within fixed bounds."""
    lower, upper = _IDENTIFIER_WIDTH
    longest = max((len(entry.identifier) for entry in results), default=lower)
    return min(max(longest, lower), upper)
