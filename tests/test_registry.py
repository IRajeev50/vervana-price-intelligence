"""Registry seeding, alias many-to-many, polymorphic pointer validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from vervana.db.base import AliasSourceType, CanonicalType
from vervana.models.entities import Alias, Commodity
from vervana.repository.registry import add_alias, counts, resolve_canonical, seed_registry

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


def test_seed_loads_registry(session: Session):
    result = seed_registry(session, SEED_DIR)
    assert result["commodity"] >= 25
    assert result["market"] >= 5
    assert result["variety"] >= 10
    # Every commodity got a verified official English alias.
    assert result["alias"] >= result["commodity"]


def test_alias_many_to_many_same_text_two_canonicals(session: Session):
    # "mirchi" can mean chilli OR capsicum — both allowed, no unique constraint.
    chilli = Commodity(canonical_name="Green Chilli")
    capsicum = Commodity(canonical_name="Capsicum")
    session.add_all([chilli, capsicum])
    session.flush()

    add_alias(
        session,
        alias_text="mirchi",
        alias_language="hi-Latn",
        alias_source_type=AliasSourceType.trader_colloquial,
        canonical_type=CanonicalType.commodity,
        canonical_id=chilli.id,
    )
    add_alias(
        session,
        alias_text="mirchi",
        alias_language="hi-Latn",
        alias_source_type=AliasSourceType.trader_colloquial,
        canonical_type=CanonicalType.commodity,
        canonical_id=capsicum.id,
    )
    both = session.query(Alias).filter(Alias.alias_text == "mirchi").all()
    assert {a.canonical_id for a in both} == {chilli.id, capsicum.id}


def test_add_alias_is_unverified_and_enqueued(session: Session):
    c = Commodity(canonical_name="Potato")
    session.add(c)
    session.flush()
    alias = add_alias(
        session,
        alias_text="aloo",
        alias_language="hi-Latn",
        alias_source_type=AliasSourceType.hinglish_transliteration,
        canonical_type=CanonicalType.commodity,
        canonical_id=c.id,
        method="lexical",
        score=95.0,
    )
    assert not alias.is_verified  # automated matches are never trusted on their own
    assert counts(session)["alias"] == 1


def test_dangling_pointer_rejected(session: Session):
    with pytest.raises(ValueError, match="does not exist"):
        add_alias(
            session,
            alias_text="ghost",
            alias_language="en",
            alias_source_type=AliasSourceType.trader_colloquial,
            canonical_type=CanonicalType.commodity,
            canonical_id=99999,
        )


def test_resolve_canonical(session: Session):
    c = Commodity(canonical_name="Onion")
    session.add(c)
    session.flush()
    assert resolve_canonical(session, CanonicalType.commodity, c.id).canonical_name == "Onion"
