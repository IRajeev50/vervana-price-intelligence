from __future__ import annotations
import io
from openpyxl import Workbook
from vervana.connectors.transcript import TranscriptConnector
from vervana.models.entities import Commodity, Market

HEADERS = ["Date", "Day", "Channel / Mandi", "Commodity", "Variety / Origin (as quoted)", "Price Low", "Price High", "Unit", "Arrivals (trucks)", "Carryover", "Market Commentary", "Raw Quote (transcript)", "Source Video", "Flag"]
def xlsx(row):
    b=Workbook(); s=b.active; s.append(HEADERS); s.append(row); out=io.BytesIO(); b.save(out); return out.getvalue()

def test_xlsx_provenance_flags_and_idempotency(session):
    session.add_all([Commodity(canonical_name="Onion"),Market(canonical_name="Azadpur",city="Delhi",state="Delhi")]); session.flush()
    row=["2026-09-09","Wed","Delhi Fruit Market (Azadpur Mandi)","Onion","Nashik",1200,1500,"50 किलो की बोरी",20,"5 trucks","firm","प्याज 1200 से 1500","https://www.youtube.com/watch?v=proof","possible merged digits in auto-transcript - verify against quote/video"]
    c=TranscriptConnector(); recs=c.records_from_upload("proof.xlsx",xlsx(row)); first=c.ingest(session,recs,mode="test"); second=c.ingest(session,recs,mode="test")
    assert (first.accepted,first.rejected)==(1,0)
    assert (second.accepted,second.reason_counts)==(0,{"duplicate_already_ingested":1})
    from vervana.models.observations import PriceObservation
    o=session.query(PriceObservation).one(); assert o.source_class.value=="quote_indicative"; assert '"source_type": "youtube_ground_proof"' in o.raw_quote; assert "possible merged digits" in o.raw_quote; assert o.canonical_price_paise_per_kg is None

def test_ambiguous_commodity_is_not_guessed(session):
    session.add_all([Commodity(canonical_name="Mango"),Market(canonical_name="Keshopur",city="Delhi",state="Delhi")]); session.flush()
    row=["2026-09-09","Wed","The Solanki Vlog (Keshopur Mandi)","Mango + Fruits (all)","",1000,1200,"","","","","quote","https://www.youtube.com/watch?v=ambiguous",""]
    c=TranscriptConnector(); result=c.ingest(session,c.records_from_upload("proof.xlsx",xlsx(row)),mode="test")
    assert result.accepted==0; assert list(result.reason_counts)==["unresolved_commodity: Mango + Fruits (all)"]
