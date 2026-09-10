"""Field observers (Part 4.3 / R11).

An observer who reports prices may themselves trade in those commodities — a structural
conflict of interest. The schema records each observer's identity AND whether they trade
in what they report, so every observation can be filtered by the observer's independence.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base


class Observer(Base):
    __tablename__ = "observer"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(80))  # e.g. "commission agent", "loader", "staff"

    # RISK[R11-RECORDER-CONFLICT]: A paid recorder who holds positions in the commodities
    # they report has a structural incentive to misreport. This flag is mandatory and every
    # observation inherits the observer's independence, so conflicted reports can always be
    # filtered out or down-weighted. Never treat a conflicted observer's quote as neutral.
    # Evidence: docs/RISK_REGISTER.md#r11-recorder-conflict
    # Verdict: PENDING
    trades_in_reported_commodities: Mapped[bool] = mapped_column(Boolean)

    notes: Mapped[str | None] = mapped_column(Text, default=None)

    @property
    def is_independent(self) -> bool:
        return not self.trades_in_reported_commodities
