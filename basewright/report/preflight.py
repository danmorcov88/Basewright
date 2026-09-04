"""What a preflight run says for itself.

Refusal is a first-class outcome, so it gets a rendering rather than an error message.
The reader is somebody deciding whether to change a machine or a request, and what they
need is the rule, the number that was found, the number that was wanted, and what would
have to change. Everything here exists to put those four things next to each other.

Only what did not pass is printed. The counts say how many rules agreed; naming each of
them would bury the two lines somebody has to act on under eighteen they do not. What was
checked in full is in the machine-readable document, where a reader who wants the whole
list can find it.

This is not :mod:`basewright.report.problems`, which refuses a *document* and reports a
file, a location and a schema violation. A preflight refuses a *host*: there is no file to
point at, severity is what orders the report, and the observed value is the whole of what
makes it useful. The two share their wrapping and their width, which is the part that
would drift if it were written twice.

ASCII only. This is read in a terminal, in a task log and in a documentation image
generated on a machine that may not agree with this one about what the console encoding
is, and a report that renders differently on Windows is a report nobody can diff.
"""

from __future__ import annotations

from collections.abc import Sequence

from basewright.preflight.model import GateResult, Outcome, PreflightResult
from basewright.report.problems import REPORT_WIDTH, wrapped

#: Width of the identifier column, clamped so one long rule id cannot push every observed
#: value off the right-hand edge.
_IDENTIFIER_WIDTH = (20, 24)

#: What each outcome is labelled, padded to one width so the labels read down as a column.
_LABEL: dict[Outcome, str] = {
    Outcome.BLOCK: "BLOCK",
    Outcome.WARN: "WARN ",
    Outcome.SKIP: "SKIP ",
    Outcome.PASS: "PASS ",
}

#: The marker on a remedy, and on the continuation of one.
_REMEDY = "-> "

#: Hanging indent of the verdict, under the word that labels it.
_VERDICT_INDENT = 9


def render_preflight(result: PreflightResult) -> str:
    """The whole rendering: what was asked, what did not pass, and the verdict."""
    lines = [
        f"PREFLIGHT  {result.host} -- {result.engine} {result.version}, instance {result.instance}",
        f"  {_counts(result)}",
    ]

    reported = [entry for entry in result.results if entry.outcome is not Outcome.PASS]
    width = _column_width(reported)
    for entry in reported:
        lines.append("")
        lines.extend(_result(entry, width))

    lines.append("")
    lines.extend(_verdict(result))
    return "\n".join(lines)


def _counts(result: PreflightResult) -> str:
    """The summary line, in the order the outcomes matter."""
    summary = result.summary
    return (
        f"{summary['pass']} pass -- {summary['warn']} warn -- "
        f"{summary['block']} block -- {summary['skip']} skipped"
    )


def _result(entry: GateResult, width: int) -> list[str]:
    """One rule: what it found, and what would change it.

    The identifier is what somebody greps for and the observed value is what they act on,
    so those two share the first line. The rule's title is in the document rather than
    here: beside an observed value that already names what was measured, it reads as the
    same sentence written twice.
    """
    label = _LABEL[entry.outcome]
    margin = 2 + len(label) + 1 + width + 2
    indent = " " * margin

    observed = wrapped(entry.observed, width=REPORT_WIDTH - margin) or [""]
    if len(entry.identifier) > width:
        # An identifier wider than its column takes a line of its own rather than
        # pushing that one result out of alignment with every other one.
        lines = [f"  {label} {entry.identifier}", f"{indent}{observed[0]}"]
    else:
        lines = [f"  {label} {entry.identifier.ljust(width)}  {observed[0]}"]
    lines.extend(f"{indent}{line}" for line in observed[1:])

    if entry.remediation and entry.outcome is not Outcome.PASS:
        remedy = wrapped(entry.remediation, width=REPORT_WIDTH - margin - len(_REMEDY))
        continued = " " * len(_REMEDY)
        lines.extend(
            f"{indent}{_REMEDY if index == 0 else continued}{line}"
            for index, line in enumerate(remedy)
        )
    return lines


def _verdict(result: PreflightResult) -> list[str]:
    """The one line somebody reads first, and sometimes the only one they read."""
    if result.blocked:
        blocks = result.counting(Outcome.BLOCK)
        rules = "rule blocks" if blocks == 1 else "rules block"
        return _hanging(
            "REFUSED",
            f"{blocks} {rules} this host. No plan was produced, and there is no flag that "
            "produces one.",
        )
    if result.warnings:
        noun = "warning" if result.warnings == 1 else "warnings"
        return _hanging(
            "PASSED",
            f"this host can be provisioned -- {result.warnings} {noun} require "
            "acknowledgement before apply will run.",
        )
    return _hanging("PASSED", "this host can be provisioned, with nothing to acknowledge.")


def _hanging(label: str, text: str) -> list[str]:
    """A labelled verdict, wrapped under itself rather than off the edge."""
    indent = " " * _VERDICT_INDENT
    lines = wrapped(text, width=REPORT_WIDTH - _VERDICT_INDENT)
    head = f"{label.ljust(_VERDICT_INDENT)}{lines[0]}"
    return [head, *(f"{indent}{line}" for line in lines[1:])]


def _column_width(results: Sequence[GateResult]) -> int:
    """Width of the identifier column: the longest identifier, within fixed bounds."""
    lower, upper = _IDENTIFIER_WIDTH
    longest = max((len(entry.identifier) for entry in results), default=lower)
    return min(max(longest, lower), upper)
