"""Spices Board of India FPO/FPC directory (official, consent-clean).

The Spices Board publishes a state-wise directory of Farmer Producer
Organisations / Companies (sourced from NABARD & SFAC) that grow spices, with
contact numbers and the spices each produces. This is the multi-commodity twin
of the CDB coconut import: one FPO that grows Pepper, Ginger and Turmeric
becomes one supplier row per commodity, so a buyer choosing "Black pepper" or
"Turmeric" on the sourcing board sees the real producers for it.

Only spices that map to a priced canonical commodity are imported (so the
supplier actually surfaces under a commodity the platform tracks); the rest are
skipped, not invented. Parsing is block-based and order-independent: within each
FPO block every phone/email/spice is collected wherever it sits, and the name is
the text before the first contact - robust to this PDF's messy column wrapping.
No individual is scraped; these are official producer organisations, sourced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SPICES_URL = "https://www.indianspices.com/sites/default/files/FPO_List_2021.pdf"
SOURCE_NAME = "Spices Board of India - FPO/FPC directory (source: NABARD/SFAC)"
ORG_TYPE = "Spice FPO / FPC"

# Spice name in the directory -> priced canonical commodity in this platform.
SPICE_TO_COMMODITY: dict[str, str] = {
    "pepper": "Black pepper",
    "turmeric": "Turmeric",
    "ginger": "Ginger",
    "chilli": "Dry Chillies",
    "chillies": "Dry Chillies",
    "tamarind": "Tamarind Fruit",
}

_STATES = [
    "Kerala",
    "Tamil Nadu",
    "Karnataka",
    "Andhra Pradesh",
    "Telangana",
    "Maharashtra",
    "Gujarat",
    "Odisha",
    "West Bengal",
    "Assam",
    "Sikkim",
    "Nagaland",
    "Mizoram",
    "Tripura",
    "Meghalaya",
    "Manipur",
    "Arunachal Pradesh",
    "Madhya Pradesh",
    "Rajasthan",
    "Goa",
    "Chhattisgarh",
    "Bihar",
    "Jharkhand",
    "Uttar Pradesh",
    "Uttarakhand",
    "Himachal Pradesh",
    "Punjab",
    "Haryana",
]
_HDR = re.compile(r"^\s*(\d+)\s+(" + "|".join(re.escape(s) for s in _STATES) + r")\b\s*(.*)$")
_SECTION = re.compile(r"^\d+\.\s+[A-Z][A-Z &]+$")  # e.g. "2. TAMIL NADU"
_PHONE = re.compile(r"\b([6-9]\d{9})\b")
_EMAIL = re.compile(r"[\w.\-]+@[\w.\-]+\.\w+")
_SPICE = re.compile(r"\b(pepper|turmeric|ginger|chill(?:i|ies)|tamarind)\b", re.IGNORECASE)
_DESIG = re.compile(
    r"\s+(Director|CEO|Chairman|Manager|President|Secretary|Contact|Mob(?:ile)?|Ph(?:one)?|Cell)\b.*$",
    re.IGNORECASE,
)


@dataclass
class FpoRecord:
    name: str
    state: str | None
    district: str | None
    phone: str | None
    email: str | None
    commodities: list[str] = field(default_factory=list)


def parse_spices_text(text: str) -> list[FpoRecord]:
    """Parse the extracted Spices Board FPO PDF into one record per FPO.

    Each FPO block is scanned as a whole (order-independent): all phones/emails/
    spices are collected wherever they appear, so column wrapping cannot misfile
    them; the name is the text before the first contact.
    """
    blocks: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _HDR.match(line)
        if m:
            if cur is not None:
                blocks.append(cur)
            cur = {"state": m.group(2), "rest": m.group(3).strip(), "lines": []}
        elif cur is not None:
            if _SECTION.match(line):  # a new "N. STATE" section ends the current block
                blocks.append(cur)
                cur = None
                continue
            cur["lines"].append(line)
    if cur is not None:
        blocks.append(cur)

    out: list[FpoRecord] = []
    for b in blocks:
        full = re.sub(r"\s+", " ", (b["rest"] + " " + " ".join(b["lines"])).strip())
        phones = _PHONE.findall(full)
        emails = _EMAIL.findall(full)
        spices = {s.lower() for s in _SPICE.findall(full)}
        commodities = sorted({SPICE_TO_COMMODITY[s] for s in spices if s in SPICE_TO_COMMODITY})
        if not commodities:
            continue  # no priced commodity to surface it under -> skip, never invent
        # Name = text before the first phone/email; the district sits before "M/s".
        firsts = [x.start() for x in (_PHONE.search(full), _EMAIL.search(full)) if x]
        head = full[: min(firsts)].strip(" ,.-") if firsts else full.strip(" ,.-")
        ms = re.search(r"M/?s\.?", head, re.IGNORECASE)
        district = None
        name = head
        if ms:
            district = head[: ms.start()].strip(" ,.-") or None
            name = head[ms.start() :].strip()
        name = _DESIG.sub("", name).strip(" ,.-")[:160]
        if district:
            district = " ".join(district.split()[:2])  # first words = the location column
        out.append(
            FpoRecord(
                name=name,
                state=b["state"],
                district=district,
                phone=phones[0] if phones else None,
                email=emails[0] if emails else None,
                commodities=commodities,
            )
        )
    return out


def extract_pdf_text(pdf_bytes: bytes) -> str:
    import io
    import logging

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def fetch_pdf(url: str = SPICES_URL) -> bytes:
    import httpx

    resp = httpx.get(url, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def build_supplier_records(
    *, url: str = SPICES_URL, pdf_bytes: bytes | None = None
) -> tuple[list[dict], str]:
    """One supplier-import dict per (FPO x mapped commodity)."""
    if pdf_bytes is None:
        pdf_bytes = fetch_pdf(url)
    fpos = parse_spices_text(extract_pdf_text(pdf_bytes))
    records: list[dict] = []
    for f in fpos:
        if not f.name:
            continue
        for commodity in f.commodities:
            records.append(
                {
                    "commodity": commodity,
                    "name": f.name,
                    "org_type": ORG_TYPE,
                    "state": f.state,
                    "district": f.district,
                    "address": None,  # this PDF's address column is unreliable - omit, never guess
                    "contact_name": None,
                    "phone": f.phone,
                    "email": f.email,
                    "source": SOURCE_NAME,
                    "source_url": url,
                }
            )
    return records, url
