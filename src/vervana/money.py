"""Money handling policy: integer paise, never floats (Part 7).

All monetary values in the system are integers counting paise (1 rupee = 100
paise). Floats are banned because they silently lose precision and the product's
credibility rests on numbers being exactly what their evidence says.

Parsing accepts strings that may carry a rupee sign, commas, and up to two
decimal places. More than two decimal places is an error, not a rounding
opportunity — we do not invent precision that the source did not state.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_RUPEE_CLEAN = re.compile(r"[₹,\s]")


class MoneyParseError(ValueError):
    """Raised when a monetary string cannot be parsed to exact paise."""


def rupees_to_paise(value: str | int | Decimal) -> int:
    """Convert a rupee amount to integer paise, exactly.

    Accepts:
      * int      -> treated as whole rupees (e.g. 45 -> 4500 paise)
      * Decimal  -> exact rupees (e.g. Decimal('45.50') -> 4550)
      * str      -> may include '₹', commas, spaces; at most 2 decimal places

    Never accepts float: floats cannot represent 45.50 exactly, so allowing them
    would smuggle imprecision into the one place we forbid it.
    """
    if isinstance(value, float):
        raise MoneyParseError(
            "float is not accepted for money; pass a str or Decimal to keep exact paise."
        )

    if isinstance(value, int):
        return value * 100

    if isinstance(value, str):
        cleaned = _RUPEE_CLEAN.sub("", value)
        if cleaned == "":
            raise MoneyParseError("empty monetary string")
        try:
            dec = Decimal(cleaned)
        except InvalidOperation as exc:
            raise MoneyParseError(f"cannot parse money from {value!r}") from exc
    elif isinstance(value, Decimal):
        dec = value
    else:  # pragma: no cover - defensive
        raise MoneyParseError(f"unsupported money type: {type(value)!r}")

    # Reject sub-paise precision rather than rounding it away.
    if -dec.as_tuple().exponent > 2:
        raise MoneyParseError(
            f"{value!r} has sub-paise precision; money is exact to 2 decimal places."
        )

    paise = (dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(paise)


def paise_to_rupee_str(paise: int) -> str:
    """Format integer paise as a rupee string, e.g. 4550 -> '₹45.50'."""
    if not isinstance(paise, int):
        raise MoneyParseError("paise must be an int")
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}₹{whole}.{frac:02d}"
