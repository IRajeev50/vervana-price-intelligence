"""Money policy: integer paise, exact, never float."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vervana.money import MoneyParseError, paise_to_rupee_str, rupees_to_paise


def test_string_with_rupee_and_decimals() -> None:
    assert rupees_to_paise("₹45.50") == 4550
    assert rupees_to_paise("45.50") == 4550
    assert rupees_to_paise("1,234.05") == 123405


def test_whole_rupee_int() -> None:
    assert rupees_to_paise(45) == 4500


def test_decimal_exact() -> None:
    assert rupees_to_paise(Decimal("45.50")) == 4550


def test_float_is_rejected() -> None:
    # Floats cannot represent 45.50 exactly; reject rather than smuggle imprecision.
    with pytest.raises(MoneyParseError):
        rupees_to_paise(45.50)  # type: ignore[arg-type]


def test_sub_paise_precision_rejected() -> None:
    with pytest.raises(MoneyParseError):
        rupees_to_paise("45.505")


def test_empty_and_garbage_rejected() -> None:
    with pytest.raises(MoneyParseError):
        rupees_to_paise("₹")
    with pytest.raises(MoneyParseError):
        rupees_to_paise("abc")


def test_format_roundtrip() -> None:
    assert paise_to_rupee_str(4550) == "₹45.50"
    assert paise_to_rupee_str(123405) == "₹1234.05"
    assert paise_to_rupee_str(-4550) == "-₹45.50"
    # Round-trip: string -> paise -> string.
    assert paise_to_rupee_str(rupees_to_paise("₹45.50")) == "₹45.50"
