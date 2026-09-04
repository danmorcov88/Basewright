"""What a plan says for itself, to the person who has to approve it.

This renders the *document*, not the objects the planner used to build one. That is not a
convenience: verify reads `plan.json` back off a disk months later and has to render it
the same way, and a plan handed to a second person is a file rather than a run. Rendering
from the artifact means there is one rendering, proven against the thing that actually
travels, instead of two that agree until somebody changes a field.

The reader is deciding whether to change a machine. What they need, in this order: what
was asked for, what the machine is, what preflight made of it, every value with the rule
and the reasoning behind it, where the files go, and everything apply would do. The
verdict is last because it is the sentence they act on and it should be the one nearest
their cursor.

Two things the sample in the brief does differently, and both are deliberate. The
punctuation here is ASCII, because this is read in a terminal, in a task log, and in a
documentation image generated on a machine that may not agree with this one about console
encodings. And preflight prints only what did not pass -- the counts say how many rules
agreed, and naming each of them buries the two lines somebody has to act on.

Every rule's reasoning is printed in full. A number without a reason is the situation this
project exists to end, and a reason trimmed to fit a column is a number with a fragment of
one. The report is long because the artifact is the product.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from basewright.report.problems import REPORT_WIDTH, wrapped
from basewright.units import render_bytes

__all__ = ["render_plan"]

#: Width of the label column in the two-column sections. Wide enough for the longest
#: label any of them uses, so that the sections line up with one another down the page.
_LABEL_WIDTH = 18

#: Indent of a section's body, and of a verdict wrapped under its own label.
_INDENT = 2
_VERDICT_INDENT = 9

#: What each gate outcome is labelled, padded to one width so they read down as a column.
_OUTCOME: dict[str, str] = {"block": "BLOCK", "warn": "WARN ", "skip": "SKIP ", "pass": "PASS "}

#: The marker on a remedy, and on the reasoning under a parameter.
_REMEDY = "-> "

#: How a change is marked. Add and modify, because apply creates and configures and there
#: is no third thing for it to do.
_ACTION: dict[str, str] = {"add": "+", "modify": "~"}


def render_plan(document: Mapping[str, Any]) -> str:
    """The whole plan, as a person reads it."""
    sections = (
        _header(document),
        _request(document),
        _host(document),
        _preflight(document),
        _parameters(document),
        _layout(document),
        _changes(document),
        _secrets(document),
        _result(document),
    )
    lines: list[str] = []
    for section in sections:
        if not section:
            continue
        if lines:
            lines.append("")
        lines.extend(section)
    return "\n".join(lines)


# ----------------------------------------------------------------------------- header


def _header(document: Mapping[str, Any]) -> list[str]:
    request = document["request"]
    return [
        f"BASEWRIGHT PLAN  {request['host']}",
        f"  generated {document['generated_at']} by basewright {document['tool_version']}"
        f" -- plan id {document['plan_id']}",
    ]


def _request(document: Mapping[str, Any]) -> list[str]:
    """What was asked for, and how much of it a person chose.

    A version somebody named and a version nobody named are not the same decision, so the
    plan says which it was rather than leaving the reader to assume the stricter one.
    """
    request = document["request"]
    profile = document["profile"]
    chosen = "requested" if request["version_source"] == "requested" else "profile default"
    return [
        "REQUEST",
        *_pairs(
            (
                ("engine", f"{request['engine']} {request['version']}  ({chosen})"),
                ("environment", request["environment"]),
                ("instance", request["instance"]),
                ("port", str(request["port"])) if "port" in request else None,
                ("profile", f"{profile['engine']} {profile['version']}"),
            )
        ),
    ]


def _host(document: Mapping[str, Any]) -> list[str]:
    """What the machine was when the decisions were made about it.

    Storage is every mount the host reported rather than only the ones a path landed on,
    because the reader deciding whether a layout is sensible needs to see what else was
    available.
    """
    host = document["host"]
    operating_system = host["os"]
    described = operating_system.get("pretty_name") or (
        f"{operating_system['distro']} {operating_system['version']}"
    )
    kernel = operating_system.get("kernel")
    lines = ["HOST"]

    pairs: list[tuple[str, str] | None] = [
        ("os", f"{described} -- {host['arch']}" + (f" -- kernel {kernel}" if kernel else "")),
        ("cpu", _counted(host["cpu"]["cores"], "core", "cores")),
        ("memory", render_bytes(host["memory"]["total_bytes"])),
    ]
    lines.extend(_pairs(pairs))

    for index, mount in enumerate(host["storage"]):
        lines.append(_pair("storage" if index == 0 else "", _mount(mount)))

    if "time_sync" in host:
        sync = host["time_sync"]
        state = "synchronized" if sync["synchronized"] else "NOT synchronized"
        lines.append(_pair("time sync", f"{sync['service']}, {state}"))
    return lines


def _mount(mount: Mapping[str, Any]) -> str:
    parts = [f"{mount['mount']}  {render_bytes(mount['free_bytes'])} free"]
    if "filesystem" in mount:
        parts.append(mount["filesystem"])
    if "rotational" in mount:
        parts.append("rotational" if mount["rotational"] else "SSD")
    return ", ".join(parts)


# --------------------------------------------------------------------------- preflight


def _preflight(document: Mapping[str, Any]) -> list[str]:
    """The counts, and then only the rules that did not simply agree."""
    summary = document["preflight"]["summary"]
    counts = (
        f"{summary['pass']} pass -- {summary['warn']} warn -- "
        f"{summary['block']} block -- {summary['skip']} skipped"
    )
    lines = [f"PREFLIGHT{' ' * (REPORT_WIDTH - len('PREFLIGHT') - len(counts))}{counts}"]

    reported = [
        result for result in document["preflight"]["results"] if result["outcome"] != "pass"
    ]
    if not reported:
        lines.append(_pair("", "every rule agreed, and none of them was skipped"))
        return lines

    width = _column_width(result["id"] for result in reported)
    for result in reported:
        lines.extend(_gate(result, width))
    return lines


def _gate(result: Mapping[str, Any], width: int) -> list[str]:
    """One rule that did not pass: what it found, and what would change it."""
    label = _OUTCOME[result["outcome"]]
    margin = _INDENT + len(label) + 1 + width + 2
    indent = " " * margin

    observed = wrapped(result.get("observed", result["title"]), width=REPORT_WIDTH - margin)
    lines = [f"{' ' * _INDENT}{label} {result['id'].ljust(width)}  {observed[0]}"]
    lines.extend(f"{indent}{line}" for line in observed[1:])
    lines.extend(_hanging_note(result.get("remediation", ""), margin))
    return lines


# -------------------------------------------------------------------------- parameters


def _parameters(document: Mapping[str, Any]) -> list[str]:
    """Every tuned value, the rule that produced it, and why that rule says so.

    Under each value, before its reasoning, is what the planner *did* to it -- held it at
    a bound, or noticed it went past a threshold the rule advises against. That is not the
    reasoning abbreviated: a reason trimmed to fit a column is worse than no reason, so
    the reasoning follows it in full. The two are kept apart because one is a fact about
    this machine and the other is the profile's argument, and they are answered to by
    different people.
    """
    parameters = document["parameters"]
    if not parameters:
        return []

    name_width = _column_width((entry["parameter"] for entry in parameters), lower=20, upper=26)
    value_width = _column_width((entry["display"] for entry in parameters), lower=10, upper=16)
    rule_width = _column_width((entry["rule"] for entry in parameters), lower=20, upper=28)

    lines = ["PARAMETERS"]
    for entry in parameters:
        head = (
            f"{' ' * _INDENT}{entry['parameter'].ljust(name_width)}  "
            f"{entry['display'].ljust(value_width)}  {entry['rule'].ljust(rule_width)}"
        )
        lines.append(head.rstrip())
        lines.extend(
            f"{' ' * (_INDENT + 2)}{line}"
            for line in wrapped(_annotation(entry), width=REPORT_WIDTH - _INDENT - 2)
        )
        lines.extend(_hanging_note(entry["why"], _INDENT + 2))
    return lines


def _annotation(entry: Mapping[str, Any]) -> str:
    """What happened to this value on its way into the plan.

    A value held at a bound says something different about the machine from one that
    landed inside its range, and a value past an advisory is the reason somebody has to
    acknowledge this plan before apply will run.
    """
    notes = []
    if entry.get("bounded_by") == "min":
        notes.append("raised to its minimum")
    elif entry.get("bounded_by") == "max":
        notes.append("held at its maximum")
    if "above_advisory" in entry:
        notes.append(f"above the {entry['above_advisory']} this rule advises")
    return "; ".join(notes)


# ------------------------------------------------------------------------------ layout


def _layout(document: Mapping[str, Any]) -> list[str]:
    layout = document["layout"]
    paths = layout["paths"]
    purpose_width = _column_width((entry["purpose"] for entry in paths), lower=8, upper=12)
    path_width = _column_width((entry["path"] for entry in paths), lower=30, upper=44)

    lines = ["LAYOUT"]
    for entry in paths:
        owner = f"{entry['owner']}:{entry['group']}"
        lines.append(
            f"{' ' * _INDENT}{entry['purpose'].ljust(purpose_width)}  "
            f"{entry['path'].ljust(path_width)}  {entry['mode']}  {owner}".rstrip()
        )

    account = layout["service_account"]
    created = "created if missing" if account["create"] else "must already exist"
    lines.append("")
    lines.extend(
        _note(
            f"Owned by {account['name']}, shell {account['shell']}, {created}. The "
            "filesystem carrying each path is in the artifact, and preflight is where "
            "two paths sharing one is reported."
        )
    )
    return lines


# ----------------------------------------------------------------------------- changes


def _changes(document: Mapping[str, Any]) -> list[str]:
    """Everything apply would do, in the order it would do it."""
    lines = ["CHANGES apply WOULD MAKE"]
    for change in document["changes"]:
        marker = _ACTION[change["action"]]
        described = change["description"]
        if "from" in change and "to" in change:
            described = f"{described} {change['from']} -> {change['to']}"
        for index, line in enumerate(wrapped(described, width=REPORT_WIDTH - _INDENT - 2) or [""]):
            prefix = f"{marker} " if index == 0 else "  "
            lines.append(f"{' ' * _INDENT}{prefix}{line}")

    lines.append("")
    lines.extend(
        _note(
            "Nothing existing is removed, and no file is overwritten without a "
            "timestamped copy left beside it."
        )
    )
    return lines


def _secrets(document: Mapping[str, Any]) -> list[str]:
    """What the instance needs that this document deliberately cannot carry."""
    secrets = document["secrets"]
    if not secrets:
        return ["SECRETS", _pair("", "this instance needs none")]

    lines = ["SECRETS"]
    for secret in secrets:
        lines.append(f"{' ' * _INDENT}{secret['name']}")
        lines.append(f"{' ' * (_INDENT + 2)}stored as {secret['location']}")
    lines.append("")
    lines.extend(
        _note(
            "Generated at apply time and written once to the secret store. This plan "
            "names where each one lives and has nowhere to put a value."
        )
    )
    return lines


# ------------------------------------------------------------------------------ result


def _result(document: Mapping[str, Any]) -> list[str]:
    """The sentence somebody acts on, and sometimes the only one they read."""
    result = document["result"]
    warnings = result["warnings"]
    if not warnings:
        text = "plan is applicable, with nothing to acknowledge."
    else:
        noun = "warning requires" if warnings == 1 else "warnings require"
        text = f"plan is applicable -- {warnings} {noun} acknowledgement before apply will run."

    indent = " " * _VERDICT_INDENT
    lines = wrapped(text, width=REPORT_WIDTH - _VERDICT_INDENT)
    return [f"{'RESULT'.ljust(_VERDICT_INDENT)}{lines[0]}", *(f"{indent}{x}" for x in lines[1:])]


# ------------------------------------------------------------------------------ shared


def _pairs(entries: Sequence[tuple[str, str] | None]) -> list[str]:
    return [_pair(entry[0], entry[1]) for entry in entries if entry is not None]


def _note(text: str) -> list[str]:
    """A sentence about the section above it, wrapped at the report's width."""
    return [f"{' ' * _INDENT}{line}" for line in wrapped(text, width=REPORT_WIDTH - _INDENT)]


def _pair(label: str, value: str) -> str:
    return f"{' ' * _INDENT}{label.ljust(_LABEL_WIDTH)}{value}".rstrip()


def _hanging_note(text: str, margin: int) -> list[str]:
    """A remedy, or a rule's reasoning, wrapped under what it explains."""
    if not text:
        return []
    indent = " " * margin
    continued = " " * len(_REMEDY)
    folded = wrapped(text, width=REPORT_WIDTH - margin - len(_REMEDY))
    return [
        f"{indent}{_REMEDY if index == 0 else continued}{line}" for index, line in enumerate(folded)
    ]


def _column_width(values: Any, *, lower: int = 20, upper: int = 24) -> int:
    """Width of a column: the longest entry, clamped so one long name cannot push the
    rest of a line off the right-hand edge."""
    longest = max((len(str(value)) for value in values), default=lower)
    return min(max(longest, lower), upper)


def _counted(total: int, singular: str, plural: str) -> str:
    return f"{total} {singular if total == 1 else plural}"
