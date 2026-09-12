"""Auditable policy-scenario analysis and dependency-free PDF export.

Magnitude bands are transparent scenario ranges, not point forecasts. They are
conditioned on the named trigger and deliberately capped when live evidence is
missing. Public-source URLs travel with every finding.
"""
from __future__ import annotations

import json
import textwrap
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Iterable

@dataclass(frozen=True)
class Source:
    title: str
    publisher: str
    url: str
    published: str

@dataclass(frozen=True)
class Scenario:
    name: str
    trigger: str
    direction: str
    magnitude_low_pct: int
    magnitude_high_pct: int
    horizon: str
    probability: str
    confidence: float
    mechanism: str
    watch: tuple[str, ...]
    source_ids: tuple[str, ...]

SOURCES = {
 "pib-ethanol": Source("Ethanol blending target and feedstock policy", "Press Information Bureau", "https://www.pib.gov.in/", "current official portal"),
 "dfpd": Source("Sugar and edible-oil policy orders", "Department of Food & Public Distribution", "https://dfpd.gov.in/", "current official portal"),
 "fao": Source("Agricultural production and climate datasets", "FAO", "https://www.fao.org/faostat/en/#data/FS", "current dataset"),
 "imd": Source("ENSO and monsoon outlooks", "India Meteorological Department", "https://mausam.imd.gov.in/", "current official portal"),
 "onion-order": Source("DGFT notification on onion export policy", "APEDA / DGFT", "https://apeda.gov.in/sites/default/files/dgft_notifications/Notification_No_28_2024_25.pdf", "2024-09-13"),
 "reuters-onion": Source("India lifts onion export ban and sets floor price", "Reuters", "https://www.reuters.com/markets/commodities/indias-government-lifts-ban-onion-exports-sets-floor-price-2024-05-04/", "2024-05-04"),
 "ie-sugar": Source("Why sugar prices are rising: stocks, output and ethanol", "The Indian Express", "https://indianexpress.com/article/explained/explained-economics/sugar-prices-rise-india-production-stocks-ethanol-explained-10844053/", "2026-08-27"),
}

LIBRARY = {
 "sugar": (
  Scenario("Higher cane diversion to ethanol", "Government raises or uncaps diversion of sugarcane juice/B-heavy molasses while closing stocks tighten", "up", 6, 14, "3-9 months", "medium", .62, "More cane-equivalent moves from crystal sugar to fuel. If output or opening stocks do not offset it, the domestic balance tightens and wholesale prices face upward pressure.", ("DFPD diversion order", "ethanol allocation by feedstock", "closing-stock/consumption ratio", "mill ex-factory price"), ("pib-ethanol","dfpd","ie-sugar")),
  Scenario("El Nino / weak monsoon in cane belts", "IMD confirms El Nino conditions and rainfall deficits persist in Maharashtra/Karnataka cane districts", "up", 8, 18, "6-12 months", "medium", .58, "Water stress reduces cane yield and recovery with a crop-cycle lag. Ethanol demand can amplify the resulting sugar-balance deficit.", ("IMD ENSO status", "district rainfall anomaly", "reservoir storage", "cane acreage and recovery"), ("imd","fao","ie-sugar")),
  Scenario("Diversion cap or stock release", "Government restricts cane-to-ethanol feedstock or releases buffer/permits imports after a price spike", "down", 4, 10, "1-4 months", "medium", .66, "Administrative supply release or lower diversion increases sugar available to the domestic market; effect fades if production remains structurally weak.", ("DFPD order", "monthly release quota", "import/export notification", "retail inflation"), ("dfpd","pib-ethanol")),
 ),
 "onion": (
  Scenario("Election-period anti-inflation intervention", "Retail onion inflation becomes politically salient and the Centre expands buffer release, export duty, MEP or export restrictions", "down", 10, 25, "2-8 weeks", "high", .72, "Export restraint and subsidised buffer sales redirect supply into domestic markets. Wholesale prices normally react faster than farm sowing can adjust.", ("retail price", "NCCF/NAFED buffer releases", "DGFT notification", "Lasalgaon arrivals"), ("onion-order","reuters-onion")),
  Scenario("Weather-led crop loss before buffer response", "Unseasonal rain/heat damages kharif or late-kharif crop while arrivals fall materially", "up", 20, 45, "2-10 weeks", "medium", .64, "Onion has short-run supply inelasticity and storage losses. Falling arrivals can produce a sharp spike before imports or buffer releases land.", ("mandi arrivals", "weather anomaly", "storage loss", "retail-wholesale spread"), ("imd","fao","reuters-onion")),
  Scenario("Export liberalisation into tight supply", "Export ban/MEP is removed while domestic arrivals and buffer stocks are below seasonal norms", "up", 8, 20, "2-6 weeks", "medium", .57, "External demand competes with domestic buyers. The direction can reverse quickly if government reinstates controls.", ("DGFT notification", "export volume", "buffer stock", "mandi arrivals"), ("onion-order","reuters-onion")),
 ),
}

ALIASES={"sugarcane":"sugar","sugar":"sugar","onion":"onion","onions":"onion"}

def build_policy_impact(commodity: str, price_context: dict | None = None) -> dict:
    key=ALIASES.get(commodity.strip().lower(), commodity.strip().lower())
    scenarios=list(LIBRARY.get(key, (Scenario("El Nino / rainfall shock", "IMD confirms ENSO-linked rainfall stress in the commodity's main production belt", "up", 5, 15, "crop-cycle dependent", "low", .38, "Lower yield and arrivals tighten supply. The generic band is intentionally wide until crop-specific acreage, arrivals and storage evidence are connected.", ("IMD ENSO status","district rainfall","acreage","mandi arrivals"), ("imd","fao")),)))
    source_ids=sorted({sid for s in scenarios for sid in s.source_ids})
    return {"commodity":commodity.title(),"generated_at_utc":datetime.now(timezone.utc).isoformat(),"price_context":price_context or {"observations":0,"latest_canonical_rupees":None},"method":{"statement":"Scenario-conditioned impact ranges, not deterministic forecasts.","magnitude":"Heuristic percentage change from the price at trigger time; validate through walk-forward backtests before production release.","confidence":"Capped by evidence coverage. Public-policy sources support the mechanism; live price/arrivals data must support release."},"scenarios":[asdict(s) for s in scenarios],"sources":[{"id":sid,**asdict(SOURCES[sid])} for sid in source_ids],"disclaimer":"Decision support only. Not trading or political advice. The model estimates commodity-price effects, not election outcomes."}

def _pdf_escape(s: str) -> str:
    return s.replace("\\","\\\\").replace("(","\\(").replace(")","\\)").encode("latin-1","replace").decode("latin-1")

def _lines(report: dict) -> Iterable[tuple[str,int]]:
    yield "V-AI POLICY & PRICE INTELLIGENCE",18
    yield f"{report['commodity']} | Scenario Impact Report",15
    yield f"Generated {report['generated_at_utc'][:10]} | India",9
    yield "",9
    pc=report['price_context']; px=pc.get('latest_canonical_rupees')
    yield (f"Platform price context: Rs {px:,.2f}/kg from {pc.get('observations',0)} observation(s)." if px is not None else "Platform price context: no verified local observation; scenario bands are unanchored."),10
    yield "",8
    yield "EXECUTIVE READ",12
    yield report['method']['statement'],10
    for s in report['scenarios']:
        yield "",7; yield s['name'].upper(),12
        yield f"Signal: {s['direction'].upper()} {s['magnitude_low_pct']}-{s['magnitude_high_pct']}% | Horizon: {s['horizon']} | Confidence: {s['confidence']:.0%}",10
        yield f"Trigger: {s['trigger']}",9
        yield f"Mechanism: {s['mechanism']}",9
        yield "Watch: " + "; ".join(s['watch']),9
    yield "",8; yield "METHOD & LIMITS",12
    yield report['method']['magnitude'],9; yield report['method']['confidence'],9
    yield "",8; yield "SOURCES",12
    for src in report['sources']: yield f"[{src['id']}] {src['publisher']}: {src['title']} ({src['published']})",8; yield src['url'],7
    yield "",8; yield report['disclaimer'],8

def render_policy_pdf(report: dict) -> bytes:
    # Small dependency-free PDF writer. Text is wrapped and paginated; URLs remain selectable.
    pages=[]; page=[]; y=790
    for raw,size in _lines(report):
        width=max(38,int(94*9/max(size,7)))
        wrapped=textwrap.wrap(str(raw),width=width,break_long_words=False,break_on_hyphens=False) or [""]
        for line in wrapped:
            if y < 55: pages.append(page); page=[]; y=790
            page.append((48,y,size,line)); y-=size+4
    if page: pages.append(page)
    objs=[]
    def add(b): objs.append(b if isinstance(b,bytes) else b.encode('latin-1')); return len(objs)
    font=add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    contents=[]; page_ids=[]
    for rows in pages:
        stream="\n".join(f"BT /F1 {s} Tf {x} {y} Td ({_pdf_escape(t)}) Tj ET" for x,y,s,t in rows).encode('latin-1')
        contents.append(add(b"<< /Length "+str(len(stream)).encode()+b" >>\nstream\n"+stream+b"\nendstream"))
        page_ids.append(add("PENDING"))
    pages_id=add("PENDING")
    for i,(pid,cid) in enumerate(zip(page_ids,contents)):
        objs[pid-1]=f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {cid} 0 R >>".encode()
    objs[pages_id-1]=f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] >>".encode()
    catalog=add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
    out=BytesIO(); out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offsets=[0]
    for i,obj in enumerate(objs,1): offsets.append(out.tell()); out.write(f"{i} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref=out.tell(); out.write(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]: out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer << /Size {len(objs)+1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()); return out.getvalue()

def render_intelligence_pdf(report: dict) -> bytes:
    """Render the platform's full signal-to-impact intelligence view as A4 PDF."""
    horizon = report.get("horizon", {})
    rows: list[tuple[str, int]] = [
        ("V-AI AGRICULTURAL INTELLIGENCE", 18),
        (f"{report.get('commodity', 'Commodity')} | Signal-to-Impact Outlook", 15),
        (f"Made {str(report.get('made_at_utc', ''))[:10]} | Honest horizon: {horizon.get('label', 'unknown')}", 9),
        ("", 8),
        ("EXECUTIVE OUTLOOK", 12),
        (f"Verdict: {report.get('verdict', 'no signal')} | Confidence: {float(report.get('confidence', 0)):.0%}", 10),
        (str(report.get("verdict_reason", "")), 9),
        (f"Horizon basis: {horizon.get('basis', 'Not available')}", 9),
        (f"Evidence coverage: {report.get('n_observed', 0)} observed | {report.get('n_simulated', 0)} simulated | {report.get('n_missing', 0)} missing", 9),
    ]
    pc = report.get("price_context", {})
    if pc.get("latest_canonical_rupees") is not None:
        rows.append((f"Latest verified price: Rs {pc['latest_canonical_rupees']:,.2f}/kg | {pc.get('observations', 0)} observation(s) | evidence #{pc.get('latest_obs_id', '-')}", 9))
    rows.extend([("", 8), ("REASONING CHAIN", 12)])
    for i, step in enumerate(report.get("steps", []), 1):
        direction = step.get("direction", "unknown")
        if hasattr(direction, "value"): direction = direction.value
        rows.append((f"{i}. {str(step.get('name', '')).upper()} | {str(direction).upper()} | confidence {float(step.get('confidence', 0)):.0%}", 10))
        rows.append((str(step.get("finding", "")), 9))
        missing = step.get("missing") or []
        if missing: rows.append(("Missing inputs: " + ", ".join(missing), 8))
    rows.extend([("", 8), ("INPUT SIGNALS", 12)])
    for sig in report.get("signals", []):
        status=sig.get("status", "missing")
        if hasattr(status, "value"): status=status.value
        val=sig.get("value_numeric") if sig.get("value_numeric") is not None else sig.get("value_text", "-")
        rows.append((f"{sig.get('kind','signal')} | {sig.get('region','India')} | {val} | {status} | {sig.get('source','')}", 8))
    rows.extend([("", 8), ("METHOD & LIMITS", 12), ("Observed, simulated and missing inputs remain visibly separate. Simulated inputs cap confidence and must not be presented as live evidence.", 9), ("Decision support only. Not trading advice. This report records what the platform knew at generation time.", 8)])
    pages=[]; page=[]; y=790
    for raw,size in rows:
        width=max(38,int(94*9/max(size,7)))
        for line in textwrap.wrap(str(raw),width=width,break_long_words=False,break_on_hyphens=False) or [""]:
            if y < 55: pages.append(page); page=[]; y=790
            page.append((48,y,size,line)); y-=size+4
    if page: pages.append(page)
    objs=[]
    def add(b): objs.append(b if isinstance(b,bytes) else b.encode("latin-1")); return len(objs)
    font=add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"); contents=[]; page_ids=[]
    for page in pages:
        stream="\n".join(f"BT /F1 {s} Tf {x} {yy} Td ({_pdf_escape(t)}) Tj ET" for x,yy,s,t in page).encode("latin-1")
        contents.append(add(b"<< /Length "+str(len(stream)).encode()+b" >>\nstream\n"+stream+b"\nendstream")); page_ids.append(add("PENDING"))
    pages_id=add("PENDING")
    for pid,cid in zip(page_ids,contents): objs[pid-1]=f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {cid} 0 R >>".encode()
    objs[pages_id-1]=f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] >>".encode(); catalog=add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
    out=BytesIO(); out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offsets=[0]
    for i,obj in enumerate(objs,1): offsets.append(out.tell()); out.write(f"{i} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref=out.tell(); out.write(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]: out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer << /Size {len(objs)+1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()); return out.getvalue()
