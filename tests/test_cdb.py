"""CDB coconut producer-company directory: parser + supplier import.

The parser is pure (works on extracted text), so no PDF/network is needed. The
guard under test that matters most: each contact attaches to the right company
even though the serial number restarts per state, so a phone is never misfiled.
"""

from __future__ import annotations

from vervana.db.base import Base
from vervana.db.engine import make_engine, session_scope
from vervana.repository.sourcing import import_suppliers, list_suppliers
from vervana.supply.cdb import parse_cdb_text

# Lines as pypdf extracts them: state headers, "serial name" CPC starts (serials
# restart per state, and the KERALA header repeats on the 2nd page), address
# lines, then contact rows.
SAMPLE = """Contact Details of Coconut Producer Companies
KERALA
1 Tejaswini
CPC
C.P.II-376/K7
Kannur-670511
Sunny George Chairman 9495147228  chairman@tejaswinicfpc.com
Shebi Zacharias  CEO 9447488037  shebi.zac@rediff.com
2 Palakkad CPC
Palakkad-678507
Vinod Kumar P CEO 9495098240  ceo@keralacoconut.com
KERALA
3 Kuttiady CPC
Babu Chairman 9846153749  babumathath@gmail.com
TAMIL NADU
1 Pudukkottai
Pudukkottai-622001
Raman Chairman 9443343108  pdk@example.com
"""


def test_parse_serials_restart_per_state_without_misfiling():
    cpcs = parse_cdb_text(SAMPLE)
    names = [c.name for c in cpcs]
    assert names == ["Tejaswini CPC", "Palakkad CPC", "Kuttiady CPC", "Pudukkottai"]
    by = {c.name: c for c in cpcs}
    # Kerala CPCs stay Kerala; the TN entry (serial restarts at 1) is Tamil Nadu.
    assert by["Tejaswini CPC"].state == "Kerala"
    assert by["Pudukkottai"].state == "Tamil Nadu"
    # Primary contact = first row with a phone; the right phone on the right company.
    assert by["Tejaswini CPC"].phone == "9495147228"
    assert by["Palakkad CPC"].phone == "9495098240"
    assert by["Pudukkottai"].phone == "9443343108"
    assert by["Tejaswini CPC"].email == "chairman@tejaswinicfpc.com"


def test_build_records_and_import_is_idempotent(monkeypatch, tmp_path):
    import vervana.supply.cdb as cdb

    monkeypatch.setattr(cdb, "extract_pdf_text", lambda _b: SAMPLE)
    records, url = cdb.build_supplier_records(pdf_bytes=b"pdf")
    assert len(records) == 4
    assert all(r["commodity"] == "Coconut" for r in records)
    assert all(r["source_url"] for r in records)  # provenance never blank

    db = f"sqlite:///{tmp_path / 'cdb.sqlite3'}"
    Base.metadata.create_all(make_engine(db))
    import os

    os.environ["VERVANA_DATABASE_URL"] = db
    with session_scope() as s:
        r1 = import_suppliers(s, records)
        assert r1["added"] == 4
    with session_scope() as s:
        r2 = import_suppliers(s, records)  # re-run: no duplicates
        assert r2["added"] == 0
        tn = list_suppliers(s, "Coconut", state="Tamil Nadu")
        assert len(tn) == 1 and tn[0]["phone"] == "9443343108"
    os.environ.pop("VERVANA_DATABASE_URL", None)
