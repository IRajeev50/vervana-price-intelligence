"""Registry repository: canonical entities, aliases, and seeding.

Adding an alias creates it *unverified* and enqueues a pending review. Promotion to
verified requires a recorded reviewer (see repository/review.py). The polymorphic
alias pointer (canonical_type + canonical_id) is validated here, since a single SQL
foreign key cannot span the four target tables.
"""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.db.base import AliasSourceType, CanonicalType
from vervana.models.entities import Alias, Commodity, Grade, Market, Variety
from vervana.models.review import AliasReview
from vervana.time import now_utc

_CANONICAL_MODEL = {
    CanonicalType.commodity: Commodity,
    CanonicalType.variety: Variety,
    CanonicalType.grade: Grade,
    CanonicalType.market: Market,
}


def resolve_canonical(session: Session, canonical_type: CanonicalType, canonical_id: int):
    """Return the canonical row, or raise if the polymorphic pointer is dangling."""
    model = _CANONICAL_MODEL[canonical_type]
    obj = session.get(model, canonical_id)
    if obj is None:
        raise ValueError(f"{canonical_type.value} id={canonical_id} does not exist")
    return obj


def add_alias(
    session: Session,
    *,
    alias_text: str,
    alias_language: str,
    alias_source_type: AliasSourceType,
    canonical_type: CanonicalType,
    canonical_id: int,
    confidence: float = 1.0,
    created_by: str = "system",
    method: str | None = None,
    score: float | None = None,
    auto_verify: bool = False,
    verified_by: str | None = None,
) -> Alias:
    """Create an alias. Unverified + pending review unless auto_verify (seed use only)."""
    resolve_canonical(session, canonical_type, canonical_id)  # validate pointer
    alias = Alias(
        alias_text=alias_text,
        alias_language=alias_language,
        alias_source_type=alias_source_type,
        canonical_type=canonical_type,
        canonical_id=canonical_id,
        confidence=confidence,
        created_by=created_by,
    )
    if auto_verify:
        alias.verified_by = verified_by or created_by
        alias.verified_at = now_utc()
    session.add(alias)
    session.flush()

    if not auto_verify:
        session.add(
            AliasReview(
                alias_id=alias.id,
                proposed_by=created_by,
                proposed_at=now_utc(),
                method=method,
                score=score,
            )
        )
        session.flush()
    return alias


def verified_aliases(session: Session) -> list[Alias]:
    """Aliases that a recorded reviewer has promoted — the resolution surface."""
    return list(session.scalars(select(Alias).where(Alias.verified_by.is_not(None))))


def counts(session: Session) -> dict[str, int]:
    """Row counts for the registry, for seed/verification reporting."""
    return {
        "commodity": session.scalar(select(func.count()).select_from(Commodity)) or 0,
        "variety": session.scalar(select(func.count()).select_from(Variety)) or 0,
        "grade": session.scalar(select(func.count()).select_from(Grade)) or 0,
        "market": session.scalar(select(func.count()).select_from(Market)) or 0,
        "alias": session.scalar(select(func.count()).select_from(Alias)) or 0,
    }


# --------------------------------------------------------------------------------------
# Seeding from checked-in CSVs (Part 3.2: seed from Agmarknet lists).
# For M1 this is a small, hand-verified bootstrap of top Delhi F&V; the full Agmarknet
# master import lands with the M2 connector when the API key is available.
# --------------------------------------------------------------------------------------


def seed_registry(session: Session, seed_dir: Path) -> dict[str, int]:
    """Idempotently seed commodities, varieties, markets, and their official aliases."""
    _seed_commodities(session, seed_dir / "commodities.csv")
    _seed_varieties(session, seed_dir / "varieties.csv")
    _seed_markets(session, seed_dir / "markets_delhi.csv")
    session.flush()
    return counts(session)


def _get_or_create_commodity(session: Session, name: str, code: str | None) -> Commodity:
    existing = session.scalar(select(Commodity).where(Commodity.canonical_name == name))
    if existing:
        return existing
    c = Commodity(canonical_name=name, agmarknet_commodity_code=code or None)
    session.add(c)
    session.flush()
    # The official English name is itself a verified alias.
    add_alias(
        session,
        alias_text=name,
        alias_language="en",
        alias_source_type=AliasSourceType.agmarknet_official,
        canonical_type=CanonicalType.commodity,
        canonical_id=c.id,
        created_by="seed",
        auto_verify=True,
    )
    return c


def _seed_commodities(session: Session, path: Path) -> None:
    for row in _read_csv(path):
        _get_or_create_commodity(session, row["canonical_name"].strip(), row.get("agmarknet_code"))


def _seed_varieties(session: Session, path: Path) -> None:
    for row in _read_csv(path):
        commodity = session.scalar(
            select(Commodity).where(Commodity.canonical_name == row["commodity"].strip())
        )
        if commodity is None:
            raise ValueError(
                f"variety '{row['canonical_name']}' references unknown commodity "
                f"'{row['commodity']}' — seed commodities first"
            )
        name = row["canonical_name"].strip()
        exists = session.scalar(
            select(Variety).where(
                Variety.commodity_id == commodity.id, Variety.canonical_name == name
            )
        )
        if exists:
            continue
        v = Variety(
            commodity_id=commodity.id,
            canonical_name=name,
            agmarknet_variety_code=row.get("agmarknet_code") or None,
        )
        session.add(v)
        session.flush()


def _seed_markets(session: Session, path: Path) -> None:
    for row in _read_csv(path):
        name = row["canonical_name"].strip()
        exists = session.scalar(select(Market).where(Market.canonical_name == name))
        if exists:
            continue
        m = Market(
            canonical_name=name,
            apmc_name=row.get("apmc_name") or None,
            city=row.get("city") or None,
            state=row.get("state") or None,
            agmarknet_market_code=row.get("agmarknet_code") or None,
        )
        session.add(m)
        session.flush()
        add_alias(
            session,
            alias_text=name,
            alias_language="en",
            alias_source_type=AliasSourceType.agmarknet_official,
            canonical_type=CanonicalType.market,
            canonical_id=m.id,
            created_by="seed",
            auto_verify=True,
        )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
