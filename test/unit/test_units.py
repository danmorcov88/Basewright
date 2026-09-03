"""Quantities, and the boundary everyone gets wrong at least once.

The failure this guards against is not a crash. It is a threshold that fires seven per
cent late because somebody read ``20GB`` as twenty-one and a half billion bytes, which
nothing reports and nobody notices until a disk fills.
"""

from __future__ import annotations

import pytest

from basewright.units import BINARY, DECIMAL, UnitError, parse_bytes, render_bytes


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("0", 0),
        ("512", 512),
        ("512B", 512),
        ("1KB", 1_000),
        ("1KiB", 1_024),
        ("128MB", 128_000_000),
        ("128MiB", 134_217_728),
        ("8GB", 8_000_000_000),
        ("8GiB", 8_589_934_592),
        ("2TB", 2_000_000_000_000),
        ("2TiB", 2_199_023_255_552),
        ("0.5GiB", 536_870_912),
        ("1.5MB", 1_500_000),
        ("  20 GB  ", 20_000_000_000),
    ],
)
def test_a_quantity_means_what_it_says(written: str, expected: int) -> None:
    assert parse_bytes(written) == expected


def test_decimal_and_binary_are_not_the_same_number() -> None:
    """The whole reason both spellings exist and neither is a synonym for the other."""
    assert parse_bytes("1GB") != parse_bytes("1GiB")
    assert parse_bytes("1GiB") - parse_bytes("1GB") == 73_741_824


def test_a_bare_number_is_already_bytes() -> None:
    """A host reports a count; a profile writes a quantity. Both arrive here."""
    assert parse_bytes(34_359_738_368) == 34_359_738_368
    assert parse_bytes(1024.0) == 1024


@pytest.mark.parametrize("written", ["", "GB", "eight gigabytes", "8 Gb B", "-1GB", "8GG"])
def test_something_that_is_not_a_quantity_is_refused(written: str) -> None:
    with pytest.raises(UnitError):
        parse_bytes(written)


def test_the_refusal_lists_the_units_that_would_have_worked() -> None:
    with pytest.raises(UnitError) as raised:
        parse_bytes("8 gigs")

    message = str(raised.value)
    assert "GiB" in message
    assert "GB" in message


def test_a_boolean_is_not_a_quantity() -> None:
    """True is an int in Python, and 1 byte is not what anybody meant by it."""
    with pytest.raises(UnitError):
        parse_bytes(True)


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "0 B"),
        (900, "900 B"),
        (1_024, "1.0 KiB"),
        (2_147_483_648, "2.0 GiB"),
        (34_359_738_368, "32.0 GiB"),
        (549_755_813_888, "512.0 GiB"),
        (2_199_023_255_552, "2.0 TiB"),
    ],
)
def test_a_count_renders_the_way_a_person_would_write_it(count: int, expected: str) -> None:
    assert render_bytes(count) == expected


def test_small_counts_are_left_alone() -> None:
    """Rounding 900 bytes to 0.9 KiB tells the reader less than the number already did."""
    assert render_bytes(1_023) == "1023 B"


def test_rendering_matches_what_the_operating_system_reports() -> None:
    """A report whose numbers cannot be checked against df is a report nobody trusts."""
    assert render_bytes(parse_bytes("32GiB")) == "32.0 GiB"


def test_every_unit_is_parseable() -> None:
    """A unit in the table that the parser rejects is a table nobody can trust."""
    for unit, size in {**DECIMAL, **BINARY}.items():
        assert parse_bytes(f"1{unit}") == size
