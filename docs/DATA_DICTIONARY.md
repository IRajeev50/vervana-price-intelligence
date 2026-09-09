# DATA DICTIONARY

Every table and column: its meaning, its source, and — crucially — **what it must never
be used for**. That last column is a first-class part of this product: the whole point is
to prevent misuse of prices that look comparable but are not.

> **Skeleton.** Tables are added as they are built. The data model lands in **M1**; this
> file is filled then. Headers and conventions are fixed now so M1 populates a known
> shape.

## Conventions (apply to every table)

- **Money:** integer **paise** columns only. Never floats. A column named `*_paise` holds
  integer paise; there are no rupee-float columns anywhere.
- **Time:** all timestamps are stored **UTC**, tz-aware, displayed IST. No naive datetimes.
- **Provenance:** any table holding an observed value carries the evidence that produced
  it; rows without traceable evidence must fail insertion.
- **Append-only where noted:** corrections insert a new row referencing `supersedes_id`;
  values are never updated in place.

## Tables

_(none yet — added in M1: `price_observation`, `commodity`, `variety`, `grade`, `market`,
`alias`, `unit_convention`, `context_signal`, `ingest_run`, and the review-queue table.)_

### Template (each table will follow this shape)

| Column | Type | Meaning | Source | **Must never be used for** |
|---|---|---|---|---|
| _example_ | _int (paise)_ | _..._ | _..._ | _e.g. "averaging across `source_class`"_ |
