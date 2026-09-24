"""Sourcing directory: real buyers and real supplier contacts (user-populated).

The sourcing layer treats each mandi/APMC as a *sourcing point* - which is real
registry data - and ranks them by estimated landed cost. These two tables hold
the ONLY things that must be entered by a human, never invented:

  * SupplierContact - an optional real contact for a market (a trader, an FPO, a
    mandi office), so a mandi-based supplier can gain a way to reach it;
  * Buyer - a real buyer (a HoReCa kitchen, a distributor) and the commodities
    they want.

Both carry a mandatory `source` (who entered/where it came from): a contact
without a provenance is exactly the fabrication this platform refuses. No row
here is seeded with example contacts.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime


class SupplierContact(Base):
    __tablename__ = "supplier_contact"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The sourcing point this contact belongs to (a registry market).
    market_id: Mapped[int] = mapped_column(ForeignKey("market.id"), index=True)
    contact_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(80), default="")  # trader / FPO / mandi office
    phone: Mapped[str | None] = mapped_column(String(40), default=None)
    email: Mapped[str | None] = mapped_column(String(160), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    # Provenance is mandatory: who supplied this, or where it was verified from.
    source: Mapped[str] = mapped_column(String(200))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Supplier(Base):
    """A commodity supplier ORGANISATION - e.g. a Coconut Producer Company from the
    official CDB directory. Distinct from SupplierContact (which attaches a contact
    to a mandi): these are producer orgs, not mandis, imported from an official,
    consent-clean directory. Provenance (source + source_url) is mandatory.
    """

    __tablename__ = "supplier"

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(200))
    org_type: Mapped[str] = mapped_column(String(80), default="")  # e.g. Coconut Producer Company
    state: Mapped[str | None] = mapped_column(String(80), default=None, index=True)
    district: Mapped[str | None] = mapped_column(String(80), default=None)
    address: Mapped[str | None] = mapped_column(Text, default=None)
    contact_name: Mapped[str | None] = mapped_column(String(160), default=None)
    phone: Mapped[str | None] = mapped_column(String(40), default=None)
    email: Mapped[str | None] = mapped_column(String(160), default=None)
    source: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime)

    __table_args__ = (
        UniqueConstraint("commodity", "name", "state", name="uq_supplier_commodity_name_state"),
    )


class Buyer(Base):
    __tablename__ = "buyer"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(60), default="")  # restaurant / hotel / distributor
    city: Mapped[str | None] = mapped_column(String(80), default=None)
    state: Mapped[str | None] = mapped_column(String(80), default=None)
    # Comma-separated canonical commodity names this buyer sources.
    commodities: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str | None] = mapped_column(String(40), default=None)
    email: Mapped[str | None] = mapped_column(String(160), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str] = mapped_column(String(200))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime)
