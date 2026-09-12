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

# Potato policy model and policy-brief decision layer ---------------------------------
LIBRARY["potato"] = (
    Scenario("Cold-store release stays orderly", "Stored crop is released in line with seasonal demand and mandi arrivals remain near normal", "neutral", -5, 6, "4-12 weeks", "medium", .56, "Potato supply is shifted across months through cold storage. Orderly drawdown prevents a harvest glut without creating a late-season shortage.", ("Agmarknet modal price and arrivals", "NHB cold-store capacity/occupancy", "release pace", "retail-wholesale spread"), ("fao",)),
    Scenario("Stock concentration / delayed release", "Cold-store holdings remain concentrated or release slows while open-market arrivals weaken", "up", 12, 28, "3-10 weeks", "medium", .61, "A large share of marketable supply is time-shifted through storage. Slower release tightens spot availability and amplifies bargaining power upstream.", ("weekly arrivals", "store occupancy", "release volumes", "regional price dispersion"), ("fao",)),
    Scenario("Harvest glut or distress unloading", "Fresh arrivals jump above seasonal norms, storage access is constrained, or financing forces early sales", "down", 15, 35, "1-6 weeks", "medium", .64, "Perishability and limited accessible storage make short-run supply inelastic. Forced selling can push farm-gate and mandi prices below production economics.", ("daily arrivals", "farm-gate/modal spread", "storage tariff", "credit availability"), ("fao",)),
    Scenario("Government market intervention", "A sharp retail rise triggers stock monitoring, subsidised sale, import facilitation or anti-hoarding enforcement", "down", 8, 20, "2-8 weeks", "low", .48, "Administrative releases and enforcement can increase visible supply and compress margins, but the effect depends on intervention volume and timing.", ("Consumer Affairs notices", "state stock limits", "import/export action", "retail inflation"), ("fao",)),
)
SOURCES["nhb-cold"] = Source("Cold-storage schemes, capacity studies and price-arrival bulletins", "National Horticulture Board", "https://www.nhb.gov.in/subsidy_claim_cold_storage.html", "current official portal")
# Attach the official storage source to potato scenarios.
LIBRARY["potato"] = tuple(Scenario(**{**asdict(s), "watch": tuple(s.watch), "source_ids": tuple(list(s.source_ids)+["nhb-cold"])}) for s in LIBRARY["potato"])
ALIASES["potatoes"] = "potato"

def build_decision_brief(commodity: str, price_context: dict | None = None, intelligence: dict | None = None) -> dict:
    impact = build_policy_impact(commodity, price_context)
    pc = impact["price_context"]
    px = pc.get("latest_canonical_rupees")
    present = {
        "price": f"Rs {px:,.2f}/kg" if px is not None else "Not verified",
        "price_note": f"Based on {pc.get('observations',0)} platform observation(s)." if px is not None else "Refresh the commodity feed before making a price-sensitive decision.",
        "stock": "Feed not connected",
        "stock_note": "NHB capacity is context, not current stock. Occupancy, release pace and ownership concentration must be collected separately.",
        "active_drivers": [s["name"] for s in impact["scenarios"][:3]],
    }
    direction_scores={"up":1,"down":-1,"neutral":0}
    weighted=sum(direction_scores.get(s["direction"],0)*s["confidence"] for s in impact["scenarios"])
    forward = "upside risk dominates" if weighted>.35 else ("downside risk dominates" if weighted<-.35 else "two-sided / range-bound risk")
    decisions = {
      "buyer": ["Stage purchases rather than locking the full requirement at one price.", "Escalate when arrivals weaken for two consecutive readings and storage release also slows.", "Separate physical availability risk from quoted-price noise."],
      "seller": ["Compare carrying cost and spoilage risk with the scenario price band before holding stock.", "Use staggered releases; do not treat a policy headline as a durable trend without arrival confirmation.", "Document grade, location and storage condition because the platform price is not automatically your realisable price."],
      "policymaker": ["Monitor farm-gate, mandi and retail prices together so intervention does not solve consumer inflation by creating farmer distress.", "Track occupancy and release concentration, not capacity alone.", "Publish intervention trigger, volume and exit rule to reduce avoidable volatility."],
    }
    impact.update({"present":present,"forward_read":forward,"decisions":decisions,"intelligence":intelligence or {}})
    return impact

# Professional policy-document PDF renderer. Pure PDF keeps local install dependency-free.
class _BriefPDF:
    W,H=595,842
    NAVY=(0.055,0.12,0.22); BLUE=(0.05,0.38,0.62); SKY=(0.90,0.95,0.98); INK=(0.08,0.11,0.16); GREY=(0.38,0.43,0.49); LINE=(0.82,0.85,0.88); WHITE=(1,1,1); RED=(0.68,0.12,0.15); GREEN=(0.06,0.45,0.27); AMBER=(0.80,0.47,0.06)
    def __init__(self,title,subtitle): self.title=title; self.subtitle=subtitle; self.pages=[]; self.ops=[]; self.y=0; self.page_no=0; self.new_page(cover=True)
    @staticmethod
    def esc(s): return _pdf_escape(str(s))
    @staticmethod
    def rgb(c): return " ".join(f"{v:.3f}" for v in c)
    def rect(self,x,y,w,h,fill,stroke=None): self.ops.append(f"q {self.rgb(fill)} rg {x} {y} {w} {h} re f Q");
    def text(self,x,y,s,size=9,color=None,bold=False): color=color or self.INK; font="F2" if bold else "F1"; self.ops.append(f"BT {self.rgb(color)} rg /{font} {size} Tf {x} {y} Td ({self.esc(s)}) Tj ET")
    def line(self,x1,y1,x2,y2,color=None,w=.6): color=color or self.LINE; self.ops.append(f"q {self.rgb(color)} RG {w} w {x1} {y1} m {x2} {y2} l S Q")
    def new_page(self,cover=False):
        if self.ops: self.pages.append(self.ops)
        self.ops=[]; self.page_no+=1; self.rect(0,0,self.W,self.H,self.WHITE)
        if cover:
            self.rect(0,670,self.W,172,self.NAVY); self.rect(0,654,self.W,16,self.BLUE)
            self.text(46,795,"V-AI  |  AGRICULTURAL INTELLIGENCE",9,self.WHITE,True)
            self.text(46,744,self.title,24,self.WHITE,True); self.text(46,714,self.subtitle,12,(.75,.84,.92))
            self.text(46,683,"POLICY & DECISION BRIEF",9,self.WHITE,True); self.y=620
        else:
            self.rect(0,807,self.W,35,self.NAVY); self.text(38,819,"V-AI  |  "+self.title,9,self.WHITE,True); self.y=782
    def footer(self,ops,page,total):
        ops.append(f"q {self.rgb(self.LINE)} RG .6 w 38 35 m 557 35 l S Q")
        ops.append(f"BT {self.rgb(self.GREY)} rg /F1 7 Tf 38 21 Td ({self.esc('Decision support, not trading advice | Generated '+datetime.now(timezone.utc).date().isoformat())}) Tj ET")
        ops.append(f"BT {self.rgb(self.GREY)} rg /F2 7 Tf 525 21 Td ({page} / {total}) Tj ET")
    def need(self,h):
        if self.y-h<55:self.new_page()
    def heading(self,s,kicker=None):
        self.need(48)
        if kicker:self.text(40,self.y,kicker.upper(),7,self.BLUE,True);self.y-=13
        self.text(40,self.y,s,15,self.NAVY,True);self.y-=11;self.line(40,self.y,555,self.y,self.BLUE,1.4);self.y-=18
    def para(self,s,size=9,color=None,indent=0,leading=None):
        leading=leading or size+4; width=max(42,int((92-indent/6)*9/size)); lines=textwrap.wrap(str(s),width=width,break_long_words=False,break_on_hyphens=False) or [""]; self.need(len(lines)*leading+3)
        for t in lines:self.text(40+indent,self.y,t,size,color);self.y-=leading
        self.y-=3
    def metric_row(self,items):
        self.need(72); n=len(items); gap=8; w=(515-gap*(n-1))/n
        for i,(label,value,note) in enumerate(items):
            x=40+i*(w+gap); self.rect(x,self.y-54,w,58,self.SKY); self.text(x+10,self.y-10,label.upper(),7,self.BLUE,True); self.text(x+10,self.y-29,value,12,self.NAVY,True); self.text(x+10,self.y-44,note[:34],7,self.GREY)
        self.y-=72
    def scenario(self,s):
        self.need(112); direction=s['direction']; col=self.RED if direction=='up' else (self.GREEN if direction=='down' else self.AMBER)
        self.rect(40,self.y-91,515,96,(.965,.97,.975)); self.rect(40,self.y-91,5,96,col)
        self.text(54,self.y-16,s['name'],11,self.NAVY,True); self.text(430,self.y-16,f"{direction.upper()} {s['magnitude_low_pct']} to {s['magnitude_high_pct']}%",9,col,True)
        self.text(54,self.y-32,f"{s['horizon']}  |  confidence {s['confidence']:.0%}  |  {s['probability']} probability",8,self.GREY)
        yy=self.y-49
        for line in textwrap.wrap("Trigger: "+s['trigger'],88,break_long_words=False)[:2]:self.text(54,yy,line,8,self.INK,True);yy-=11
        for line in textwrap.wrap(s['mechanism'],91,break_long_words=False)[:2]:self.text(54,yy,line,8,self.GREY);yy-=11
        self.y-=108
    def table(self,headers,rows,widths):
        rh=24; self.need(rh*(len(rows)+1)+10); x=40; self.rect(x,self.y-rh,515,rh,self.NAVY)
        xx=x
        for h,w in zip(headers,widths):self.text(xx+6,self.y-16,h.upper(),7,self.WHITE,True);xx+=w
        self.y-=rh
        for ri,row in enumerate(rows):
            if ri%2==0:self.rect(x,self.y-rh,515,rh,(.965,.97,.975))
            xx=x
            for val,w in zip(row,widths): self.text(xx+6,self.y-16,str(val)[:max(8,int(w/5.3))],7,self.INK);xx+=w
            self.y-=rh
        self.y-=10
    def finish(self):
        if self.ops:self.pages.append(self.ops)
        total=len(self.pages)
        for i,p in enumerate(self.pages,1):self.footer(p,i,total)
        objs=[]
        def add(b):objs.append(b if isinstance(b,bytes) else b.encode('latin-1'));return len(objs)
        f1=add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");f2=add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>");cids=[];pids=[]
        for p in self.pages:
            st="\n".join(p).encode('latin-1');cids.append(add(b"<< /Length "+str(len(st)).encode()+b" >>\nstream\n"+st+b"\nendstream"));pids.append(add("PENDING"))
        ps=add("PENDING")
        for pid,cid in zip(pids,cids):objs[pid-1]=f"<< /Type /Page /Parent {ps} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {cid} 0 R >>".encode()
        objs[ps-1]=f"<< /Type /Pages /Count {len(pids)} /Kids [{' '.join(f'{p} 0 R' for p in pids)}] >>".encode();cat=add(f"<< /Type /Catalog /Pages {ps} 0 R >>")
        out=BytesIO();out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n");off=[0]
        for i,o in enumerate(objs,1):off.append(out.tell());out.write(f"{i} 0 obj\n".encode()+o+b"\nendobj\n")
        xr=out.tell();out.write(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode());[out.write(f"{z:010d} 00000 n \n".encode()) for z in off[1:]];out.write(f"trailer << /Size {len(objs)+1} /Root {cat} 0 R >>\nstartxref\n{xr}\n%%EOF\n".encode());return out.getvalue()

def _render_brief(brief:dict, intelligence:dict|None=None)->bytes:
    p=_BriefPDF(brief['commodity']+" Market Outlook","Present position, forward scenarios and decision implications")
    p.text(46,610,"As of",8,p.GREY,True);p.text(46,590,brief['generated_at_utc'][:10],11,p.NAVY,True)
    p.text(200,610,"Geography",8,p.GREY,True);p.text(200,590,"India | commodity-specific",11,p.NAVY,True)
    p.text(402,610,"Forward read",8,p.GREY,True);p.text(402,590,brief['forward_read'].title(),10,p.NAVY,True)
    p.y=545;p.heading("Executive decision read","01")
    p.para("This brief separates what is known now from what is conditional. It joins the platform's verified price evidence with storage, arrivals, climate and policy scenarios; missing stock data is shown as missing, not estimated.",10)
    pr=brief['present'];p.metric_row([("Current price",pr['price'],pr['price_note']),("Warehouse / stock",pr['stock'],"Occupancy feed status"),("Scenario balance",brief['forward_read'].title(),"Confidence-weighted read")])
    p.heading("Present situation","02");p.para(pr['price_note']);p.para(pr['stock_note']);p.para("Active drivers: "+"; ".join(pr['active_drivers']))
    p.heading("Forward scenarios","03")
    for s in brief['scenarios']:p.scenario(s)
    p.heading("Decision matrix","04")
    rows=[]
    short={"buyer":("Stage purchases","Check arrivals + releases"),"seller":("Compare carry economics","Use staggered releases"),"policymaker":("Track 3 price levels","Publish trigger + exit rule")}
    for who in brief['decisions']: rows.append((who.title(),*short[who]))
    p.table(("Decision-maker","Act now","Escalation / check"),rows,(90,215,210))
    for who,actions in brief['decisions'].items():p.para(who.title()+": "+" ".join(actions),8)
    if intelligence:
        p.heading("Platform intelligence chain","05")
        p.metric_row([("Verdict",str(intelligence.get('verdict','no signal')),str(intelligence.get('verdict_reason',''))),("Evidence",f"{intelligence.get('n_observed',0)} observed",f"{intelligence.get('n_simulated',0)} simulated | {intelligence.get('n_missing',0)} missing"),("Confidence",f"{float(intelligence.get('confidence',0)):.0%}","Capped when simulated")])
        for i,s in enumerate(intelligence.get('steps',[]),1):
            direction=s.get('direction','unknown');direction=getattr(direction,'value',direction);p.para(f"{i}. {s.get('name','').upper()} | {str(direction).upper()} | {float(s.get('confidence',0)):.0%} - {s.get('finding','')}",8)
    p.heading("Evidence and source register","06")
    p.table(("Source","Publisher","Use in this brief"),[(s['id'],s['publisher'],s['title']) for s in brief['sources']],(90,145,280))
    for s in brief['sources']:p.para(f"[{s['id']}] {s['url']}",7,p.GREY)
    p.heading("Method, limits and next data","07");p.para(brief['method']['magnitude']);p.para(brief['method']['confidence']);p.para("Next data priority: verified current warehouse occupancy and release pace by region. Capacity alone must never be described as current stock.");p.para(brief['disclaimer'],8,p.GREY)
    return p.finish()

def render_policy_pdf(report:dict)->bytes:
    return _render_brief(report if 'present' in report else build_decision_brief(report['commodity'],report.get('price_context')))

def render_intelligence_pdf(report:dict)->bytes:
    return _render_brief(build_decision_brief(report.get('commodity','Commodity'),report.get('price_context'),report),report)

# Expanded evidence chain requested for decision briefs --------------------------------
SOURCES.update({
 "imd-agromet": Source("District agrometeorological advisories and weather bulletins", "India Meteorological Department", "https://mausam.imd.gov.in/", "current official bulletins"),
 "agmarknet": Source("Mandi price and arrivals", "AGMARKNET 2.0 / DMI", "https://agmarknet.gov.in/", "current official platform"),
 "wdra": Source("Registered warehouse directory and e-NWR ecosystem", "Warehousing Development and Regulatory Authority", "https://wdra.gov.in/", "current official registry"),
 "cwc": Source("Warehouse locations, capacity and annual reporting", "Central Warehousing Corporation", "https://cewacor.nic.in/", "current official portal"),
 "cpri": Source("Potato crop production, utilisation and processing research", "ICAR-Central Potato Research Institute", "https://cpri.icar.gov.in/", "current official research portal"),
})

def build_evidence_chain(commodity:str, price_context:dict|None=None)->list[dict]:
    pc=price_context or {}; trend=pc.get('trend_change_pct')
    trend_text=(f"{trend:+.1f}% across {pc.get('trend_sample_size',0)} recent canonical observations" if trend is not None else "No verified price trend available")
    potato=commodity.strip().lower() in {"potato","potatoes"}
    return [
      {"stage":"1. Weather -> yield","state":"data source feasible; live bulletin parser not connected","observed":False,"finding":"IMD district agromet bulletins can support crop-stage weather stress. For potato, heat during tuber initiation/bulking, frost, excess rain and late blight conditions are relevant; yield effect must be crop-stage and region specific, not a generic rainfall score.","next_data":"Parse IMD bulletin date, district, crop stage, hazard, forecast window and advisory; join to a crop sensitivity table.","sources":["imd-agromet","cpri"]},
      {"stage":"2. Mandi price + arrivals / production","state":"price data wired; arrivals field is a schema gap","observed":pc.get('latest_canonical_rupees') is not None,"finding":trend_text+". AGMARKNET 2.0 is the intended live official source. The earlier data.gov.in feed is stale and must not drive a current report.","next_data":"Add arrival_quantity, arrival_unit and market-day fields to the ingestion model; compute 7/28-day arrival anomaly and regional dispersion.","sources":["agmarknet"]},
      {"stage":"3. Consumption destinations","state":"structural map; live demand feed not connected","observed":False,"finding":("Potato demand splits across household fresh consumption, food service, processing (chips/fries/flakes), seed and wastage. Each channel has different grade, season and price sensitivity." if potato else "Map household, institutional, processing, seed/feed/export and wastage channels before inferring demand."),"next_data":"Connect official utilisation research, processor procurement and retail/HoReCa demand proxies; keep structural shares separate from live offtake.","sources":["cpri","fao"]},
      {"stage":"4. Warehouse occupancy + producer stock","state":"capacity/registry public; live occupancy and ownership generally not public","observed":False,"finding":"WDRA provides registered-facility context; NHB and CWC publish facility/capacity information. These sources do not establish today's commodity occupancy, release pace, grade or producer ownership. The report therefore shows no stock estimate.","next_data":"Node-level daily stock ledger: warehouse ID, WDRA/NHB linkage, commodity/grade, owner class, quantity in/out, occupied capacity, pledge/e-NWR status and release intention.","sources":["wdra","nhb-cold","cwc"]},
    ]

# Replace brief constructor with the richer chain while retaining stable keys.
_old_build_decision_brief = build_decision_brief
def build_decision_brief(commodity: str, price_context: dict | None = None, intelligence: dict | None = None) -> dict:
    brief=_old_build_decision_brief(commodity,price_context,intelligence)
    brief['evidence_chain']=build_evidence_chain(commodity,price_context)
    present=brief['present'];pc=brief['price_context'];trend=pc.get('trend_change_pct')
    present['price_direction']=("rising" if trend and trend>2 else ("falling" if trend and trend<-2 else ("broadly stable" if trend is not None else "unknown")))
    present['price_range']=(f"Rs {pc['recent_low_rupees']:,.2f} to {pc['recent_high_rupees']:,.2f}/kg" if pc.get('recent_low_rupees') is not None else "not available")
    present['arrivals']="Schema does not yet store arrival quantity"
    # Ensure the expanded official register appears in the brief.
    ids={s['id'] for s in brief['sources']}
    for sid in ('imd-agromet','agmarknet','wdra','nhb-cold','cwc','cpri'):
        if sid not in ids: brief['sources'].append({'id':sid,**asdict(SOURCES[sid])})
    return brief

# Enrich the professional renderer with an evidence-chain and explicit gap table.
_base_render_brief=_render_brief
def _render_brief(brief:dict, intelligence:dict|None=None)->bytes:
    # Build the base report with its policy-quality cover/scenarios/decisions.
    p=_BriefPDF(brief['commodity']+" Market Outlook","Weather, mandi, demand and warehouse evidence chain")
    p.text(46,610,"As of",8,p.GREY,True);p.text(46,590,brief['generated_at_utc'][:10],11,p.NAVY,True)
    p.text(200,610,"Geography",8,p.GREY,True);p.text(200,590,"India | commodity-specific",11,p.NAVY,True)
    p.text(402,610,"Forward read",8,p.GREY,True);p.text(402,590,brief['forward_read'].title(),10,p.NAVY,True)
    p.y=545;p.heading("Executive decision read","01");p.para("Evidence sequence: weather to crop yield; production and mandi arrivals; consumption destinations; warehouse occupancy and producer stock; then scenarios and actions. Missing links remain visible and cap confidence.",10)
    pr=brief['present'];p.metric_row([("Current price",pr['price'],"Direction: "+pr.get('price_direction','unknown')),("Recent range",pr.get('price_range','not available'),pr['price_note']),("Warehouse / stock",pr['stock'],"No occupancy estimate")])
    p.heading("Present evidence chain","02")
    for e in brief.get('evidence_chain',[]):
        p.need(105);p.text(40,p.y,e['stage'],11,p.NAVY,True);p.text(400,p.y,("OBSERVED" if e['observed'] else "DATA GAP"),8,(p.GREEN if e['observed'] else p.AMBER),True);p.y-=17;p.para(e['finding'],8);p.para("Next data: "+e['next_data'],7,p.GREY)
    p.heading("Forward scenarios","03");[p.scenario(s) for s in brief['scenarios']]
    p.heading("Decision matrix","04");short={"buyer":("Stage purchases","Check weather + arrivals + releases"),"seller":("Compare carry economics","Check storage + demand channel"),"policymaker":("Track farm/mandi/retail","Publish trigger + exit rule")};p.table(("Decision-maker","Act now","Escalation / check"),[(w.title(),*short[w]) for w in brief['decisions']],(90,190,235));[p.para(w.title()+": "+" ".join(a),8) for w,a in brief['decisions'].items()]
    if intelligence:
        p.heading("Platform intelligence chain","05");p.metric_row([("Verdict",str(intelligence.get('verdict','no signal')),str(intelligence.get('verdict_reason',''))),("Evidence",f"{intelligence.get('n_observed',0)} observed",f"{intelligence.get('n_simulated',0)} simulated | {intelligence.get('n_missing',0)} missing"),("Confidence",f"{float(intelligence.get('confidence',0)):.0%}","Capped when simulated")]);[p.para(f"{i}. {s.get('name','').upper()} | {str(getattr(s.get('direction','unknown'),'value',s.get('direction','unknown'))).upper()} | {float(s.get('confidence',0)):.0%} - {s.get('finding','')}",8) for i,s in enumerate(intelligence.get('steps',[]),1)]
    p.heading("Publicly obtainable vs proprietary data","06");p.table(("Layer","Publicly feasible now","Still required"),[("Weather","IMD bulletins/advisories","Parsed crop-stage hazards"),("Mandi","AGMARKNET 2.0 prices/arrivals","Arrival fields + anomaly model"),("Demand","Official structural research","Live channel offtake"),("Warehouses","WDRA/NHB/CWC registry + capacity","Occupancy, ownership, release pace")],(95,195,225))
    p.heading("Evidence and source register","07");p.table(("Source","Publisher","Use in this brief"),[(s['id'],s['publisher'],s['title']) for s in brief['sources']],(80,145,290));[p.para(f"[{s['id']}] {s['url']}",7,p.GREY) for s in brief['sources']]
    p.heading("Method, limits and collection plan","08");p.para(brief['method']['magnitude']);p.para(brief['method']['confidence']);p.para("Implementation sequence: (1) add crop-stage weather parser; (2) migrate live mandi ingestion to AGMARKNET 2.0 and add arrival fields; (3) build consumption-channel registry and proxies; (4) onboard warehouse nodes for daily stock, ownership and releases; (5) calibrate scenario bands with walk-forward tests.");p.para("Warehouse capacity is never used as a proxy for current occupancy. Producer stock is never inferred from registration. "+brief['disclaimer'],8,p.GREY)
    return p.finish()
