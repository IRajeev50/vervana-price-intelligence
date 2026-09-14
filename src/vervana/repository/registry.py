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


def resolve_by_name(session: Session, *, name: str, canonical_type: CanonicalType) -> int | None:
    """Resolve an incoming name to a canonical id via a VERIFIED alias, else None.

    Only verified aliases are trusted (Part 3.2). Matching is on the normalised form,
    so "AZADPUR" resolves to the "Azadpur" alias. A tie across different canonicals is
    treated as unresolved (None) rather than a guess — the caller enqueues it for review.
    """
    from vervana.matching.normalize import normalize

    target = normalize(name)
    matches = {
        a.canonical_id
        for a in session.scalars(
            select(Alias).where(
                Alias.canonical_type == canonical_type,
                Alias.verified_by.is_not(None),
            )
        )
        if normalize(a.alias_text) == target
    }
    return next(iter(matches)) if len(matches) == 1 else None


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
    """Idempotently seed commodities, varieties, markets, units, and official aliases."""
    _seed_commodities(session, seed_dir / "commodities.csv")
    _seed_varieties(session, seed_dir / "varieties.csv")
    _seed_markets(session, seed_dir / "markets_delhi.csv")
    _seed_markets(session, seed_dir / "markets_national.csv")
    _seed_unit_conventions(session, seed_dir / "unit_conventions.csv")
    session.flush()
    return counts(session)


def _seed_unit_conventions(session: Session, path: Path) -> None:
    from vervana.models.units import UnitConvention

    if not path.exists():
        return
    for row in _read_csv(path):
        unit_raw = row["unit_raw"].strip()
        exists = session.scalar(
            select(UnitConvention).where(
                UnitConvention.unit_raw == unit_raw,
                UnitConvention.market_id.is_(None),
                UnitConvention.commodity_id.is_(None),
            )
        )
        if exists:
            continue
        session.add(
            UnitConvention(
                unit_raw=unit_raw,
                kg_equivalent=float(row["kg_equivalent"]),
                source=row.get("source") or "seed",
                confidence=float(row.get("confidence") or 1.0),
            )
        )
        session.flush()


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


def sync_mandis(session: Session, path: Path) -> dict:
    """Add any mandis from the config file that aren't in the registry yet.

    Adding a mandi is a CONFIG change (edit `data/config/mandis.csv`), not a code change
    (Part 6 / M8). Returns counts and the total observer headcount for the R12 estimate.
    """
    added = 0
    total_observers = 0
    n_mandis = 0
    for row in _read_csv(path):
        name = row["name"].strip()
        if not name:
            continue
        n_mandis += 1
        total_observers += int(row.get("observers") or 0)
        existing = session.scalar(select(Market).where(Market.canonical_name == name))
        if existing is not None:
            continue
        m = Market(
            canonical_name=name,
            apmc_name=row.get("apmc_name") or None,
            city=row.get("city") or None,
            state=row.get("state") or None,
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
            created_by="config",
            auto_verify=True,
        )
        added += 1
    session.flush()
    return {"added": added, "n_mandis": n_mandis, "total_observers": total_observers}


def bootstrap_from_agmarknet_records(session: Session, records: list[dict]) -> dict[str, int]:
    """Create commodities/markets (+ verified agmarknet_official aliases) from a live
    Agmarknet snapshot.

    The spec says "seed from official Agmarknet commodity and variety lists" — the live
    API *is* that official list, so names taken straight from it are recorded as
    agmarknet_official aliases and auto-verified (they are the authority, not an automated
    guess). This is what lets real prices resolve and flow into the platform.
    """
    created = {"commodity": 0, "market": 0}
    for rec in records:
        low = {str(k).strip().lower(): v for k, v in rec.items()}
        cname = str(low.get("commodity", "")).strip()
        mname = str(low.get("market", "")).strip()
        if cname:
            existing = session.scalar(select(Commodity).where(Commodity.canonical_name == cname))
            if existing is None:
                c = Commodity(canonical_name=cname)
                session.add(c)
                session.flush()
                add_alias(
                    session,
                    alias_text=cname,
                    alias_language="en",
                    alias_source_type=AliasSourceType.agmarknet_official,
                    canonical_type=CanonicalType.commodity,
                    canonical_id=c.id,
                    created_by="agmarknet",
                    auto_verify=True,
                )
                created["commodity"] += 1
        if mname:
            existing = session.scalar(select(Market).where(Market.canonical_name == mname))
            if existing is None:
                m = Market(
                    canonical_name=mname,
                    city=str(low.get("district", "")).strip() or None,
                    state=str(low.get("state", "")).strip() or None,
                )
                session.add(m)
                session.flush()
                add_alias(
                    session,
                    alias_text=mname,
                    alias_language="en",
                    alias_source_type=AliasSourceType.agmarknet_official,
                    canonical_type=CanonicalType.market,
                    canonical_id=m.id,
                    created_by="agmarknet",
                    auto_verify=True,
                )
                created["market"] += 1
    session.flush()
    return created
