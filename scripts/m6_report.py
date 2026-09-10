#!/usr/bin/env python3
"""M6 acceptance report: flag rate + sample parsed rows (incl. failures)."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from vervana.db.base import SourceClass
from vervana.db.engine import session_scope
from vervana.models.entities import Commodity, Market
from vervana.models.observations import PriceObservation


def main() -> None:
    with session_scope() as s:
        total = s.scalar(
            select(func.count())
            .select_from(PriceObservation)
            .where(PriceObservation.source_class == SourceClass.quote_indicative)
        )
        rows = list(
            s.scalars(
                select(PriceObservation)
                .where(PriceObservation.source_class == SourceClass.quote_indicative)
                .order_by(PriceObservation.id)
            )
        )
        flagged = digit_merge = kg_priced = 0
        merge_samples = []
        for o in rows:
            raw = json.loads(o.raw_quote)
            flags = raw.get("detected_flags") or []
            if flags:
                flagged += 1
            if any("digit_merge" in f for f in flags):
                digit_merge += 1
                if len(merge_samples) < 3:
                    merge_samples.append((o, raw, flags))
            if o.canonical_price_paise_per_kg is not None:
                kg_priced += 1

        print(f"accepted video-quote rows: {total}")
        print(f"  carrying a flag: {flagged} ({flagged / total:.1%})")
        print(f"  digit-merge suspected: {digit_merge}")
        print(
            f"  with canonical ₹/kg (unit stated as kg): {kg_priced} "
            f"(rest keep NULL — unit unstated, we do not guess)"
        )

        def line(o):
            c = s.get(Commodity, o.commodity_id).canonical_name
            m = s.get(Market, o.market_id).canonical_name
            lo, hi = o.price_low_paise / 100, o.price_high_paise / 100
            return f"    #{o.id} {c} @ {m}: ₹{lo:g}-{hi:g}/{o.unit_raw}"

        print("\n17 accepted sample rows:")
        for o in rows[:17]:
            print(line(o))
        print("\n3 digit-merge FLAGGED rows (flagged, never corrected):")
        for o, raw, flags in merge_samples:
            print(line(o), "|", flags)
            print(f"        quote: {str(raw.get('quote'))[:80]}")


if __name__ == "__main__":
    main()
