"""Spices Board FPO directory: parser + multi-commodity supplier import.

Pure parser (no PDF/network). Guards under test: an FPO fans out to one row per
priced commodity it grows, spices with no priced commodity are skipped (not
invented), a spice word inside the NAME does not truncate the name, and section
headers bound the blocks.
"""

from __future__ import annotations

from vervana.supply.spices_fpo import parse_spices_text

SAMPLE = """1. KERALA
S.N State Location Name & Address Contact Spices
1 Kerala Aalapuzha M/s.Onattukara Spices FPC
Director - 9446116799
onattukaraspices@gmail.com
Turmeric, Pepper,
Ginger, Spices
2 Kerala Ernakulam M/s.Nutmeg FPC Ltd
9645950388 Nutmeg, Clove
3 Kerala Idukki M/s.Pepper Growers Company Ltd
9447662163 pep@x.com Pepper
2. TAMIL NADU
1 Tamil Nadu Erode M/s.Erode Turmeric FPC
9443001122 turmeric@x.com Turmeric, Chilli
"""


def test_parse_maps_spices_and_skips_unmapped():
    fpos = parse_spices_text(SAMPLE)
    by = {f.name: f for f in fpos}
    # Nutmeg FPC grows only Nutmeg/Clove -> no priced commodity -> skipped entirely.
    assert "M/s.Nutmeg FPC Ltd" not in by
    # Onattukara fans out to its three priced spices.
    assert by["M/s.Onattukara Spices FPC"].commodities == ["Black pepper", "Ginger", "Turmeric"]
    assert by["M/s.Onattukara Spices FPC"].phone == "9446116799"
    assert by["M/s.Onattukara Spices FPC"].state == "Kerala"
    # A spice word IN the name must not truncate the name.
    assert "M/s.Pepper Growers Company Ltd" in by
    # Section header bounds the block: the Erode FPO is Tamil Nadu.
    assert by["M/s.Erode Turmeric FPC"].state == "Tamil Nadu"
    assert set(by["M/s.Erode Turmeric FPC"].commodities) == {"Turmeric", "Dry Chillies"}


def test_build_records_via_monkeypatched_text(monkeypatch):
    import vervana.supply.spices_fpo as mod

    monkeypatch.setattr(mod, "extract_pdf_text", lambda _b: SAMPLE)
    records, url = mod.build_supplier_records(pdf_bytes=b"pdf")
    # Onattukara(3) + Pepper Growers(1) + Erode(2) = 6 supplier rows; Nutmeg skipped.
    assert len(records) == 6
    assert all(r["source_url"] for r in records)  # provenance never blank
    peppers = [r for r in records if r["commodity"] == "Black pepper"]
    assert {r["name"] for r in peppers} >= {
        "M/s.Onattukara Spices FPC",
        "M/s.Pepper Growers Company Ltd",
    }
