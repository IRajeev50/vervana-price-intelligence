"""SFAC national FPO directory: pure row parser + multi-commodity fan-out.

The parser takes already-extracted table cells (pdfplumber does the PDF work), so
no PDF/network is needed here. Guards: a row fans out to one record per mapped
crop, the state's parenthetical district is stripped, the contact name is the
first non-designation line, longest crop key wins ("greengram" not "gram"), and
rows without a serial / name / mapped crop are skipped.
"""

from __future__ import annotations

from vervana.supply.sfac_fpo import parse_sfac_rows

_HDR = [
    "S. No.",
    "State Name",
    "Programme",
    "Name of Resource",
    "FPO Name",
    "Legal Form",
    "Reg No",
    "Date",
    "FPO Address",
    "Contact",
    "Major Crops",
]
ROWS = [
    _HDR,
    [
        "13",
        "Bihar",
        "VIUC",
        "Kaushalaya Foundation",
        "Harnaut kishan producer company limited",
        "Producer Company",
        "U01",
        "1-May-13",
        "H.No 77, Nalanda, Bihar",
        "Shri. Rajeev Ranjan Kumar\nDirector\nPh. No- 9570912615",
        "Potato, Tomato, Cauliflower",
    ],
    [
        "14",
        "Karnataka (Kolar)",
        "X",
        "Y",
        "Kolar Mango FPC",
        "Producer Company",
        "U02",
        "2020",
        "Kolar",
        "Ramesh\n9876500011",
        "Mango, Redgram, Greengram",
    ],
    ["x", "junk"],  # no numeric serial / short -> skipped
    [
        "15",
        "Assam",
        "Z",
        "W",
        "Barak Valley FPC",
        "Producer Company",
        "U03",
        "2019",
        "Silchar",
        "no contact here",
        "Nutmeg, Clove",  # no mapped crop -> skipped
    ],
]


def test_parse_fans_out_and_cleans():
    recs = parse_sfac_rows(ROWS)
    by = {r.name: r for r in recs}
    assert set(by) == {"Harnaut kishan producer company limited", "Kolar Mango FPC"}

    h = by["Harnaut kishan producer company limited"]
    assert h.state == "Bihar"
    assert h.phone == "9570912615"
    assert h.contact_name == "Shri. Rajeev Ranjan Kumar"  # first non-designation line
    assert h.commodities == ["Cauliflower", "Potato", "Tomato"]

    k = by["Kolar Mango FPC"]
    assert k.state == "Karnataka"  # parenthetical district stripped
    assert k.phone == "9876500011"
    # "Redgram" -> Arhar, "Greengram" -> Green Gram (longest key wins over "gram").
    assert "Mango" in k.commodities
    assert "Arhar (Tur/Red Gram)(Whole)" in k.commodities
    assert "Green Gram (Moong)(Whole)" in k.commodities


def test_unmapped_and_malformed_rows_skipped():
    recs = parse_sfac_rows(ROWS)
    # Barak Valley (nutmeg/clove only) and the junk row produce nothing.
    assert all(r.name != "Barak Valley FPC" for r in recs)
