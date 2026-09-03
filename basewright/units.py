"""Quantities of bytes, parsed once and rendered once.

Sizing rules carry bounds like ``128MB``, layouts carry thresholds like ``20GB``, hosts
report plain integers, and reports show ``32.0 GiB``. Three implementations of that
conversion would be three chances to be subtly wrong about whether a gigabyte is a
thousand megabytes or 1024 of them, and the kind of wrong that only shows up as a
threshold that fires seven per cent too late.

So both spellings are supported and both mean exactly what they say: ``GB`` is a billion
bytes and ``GiB`` is 1073741824 of them. A profile that writes ``20GB`` gets twenty
billion, not twenty-one and a half.

Reports render in binary units, because that is what an operating system reports free
space in, and a report whose numbers cannot be checked against ``df`` is a report nobody
trusts twice.
"""

from __future__ import annotations

import re

#: Decimal units. A kilobyte is a thousand bytes here, as the standard says and as disk
#: vendors have always sold them.
DECIMAL: dict[str, int] = {
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "PB": 1000**5,
}

#: Binary units. What the kernel means when it says a machine has 32 GiB of memory.
BINARY: dict[str, int] = {
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
    "PiB": 1024**5,
}

UNITS: dict[str, int] = {"B": 1, **DECIMAL, **BINARY}

#: Largest first, so rendering picks the unit a person would have chosen.
_RENDER_ORDER: tuple[tuple[str, int], ...] = (
    ("PiB", BINARY["PiB"]),
    ("TiB", BINARY["TiB"]),
    ("GiB", BINARY["GiB"]),
    ("MiB", BINARY["MiB"]),
    ("KiB", BINARY["KiB"]),
)

_QUANTITY = re.compile(r"^\s*(?P<number>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>[A-Za-z]+)?\s*$")


class UnitError(ValueError):
    """A quantity that cannot be read as a number of bytes."""


def parse_bytes(value: str | int | float) -> int:
    """Read a quantity of bytes.

    A bare number is already a count of bytes, which is how a host reports one. A string
    carries its unit, which is how a profile writes one.
    """
    if isinstance(value, bool):
        raise UnitError(f"{value!r} is not a quantity of bytes")
    if isinstance(value, int | float):
        return round(value)

    match = _QUANTITY.match(value)
    if match is None:
        raise UnitError(
            f"{value!r} is not a quantity of bytes. Write a number, optionally followed by "
            f"a unit: {', '.join(sorted(UNITS))}."
        )

    unit = match["unit"] or "B"
    if unit not in UNITS:
        raise UnitError(
            f"{unit!r} is not a unit this understands. Use one of: {', '.join(sorted(UNITS))}. "
            "Decimal and binary units are both accepted and mean what they say."
        )
    return round(float(match["number"]) * UNITS[unit])


def render_bytes(count: int) -> str:
    """Render a count of bytes the way a report should show it.

    Binary units, one decimal place, and no unit larger than the number justifies. Below a
    kibibyte the count is shown as it is: rounding 900 bytes to ``0.9 KiB`` tells the
    reader less than the number already did.
    """
    if count < 0:
        raise UnitError(f"{count} is not a quantity of bytes")
    for unit, size in _RENDER_ORDER:
        if count >= size:
            return f"{count / size:.1f} {unit}"
    return f"{count} B"
