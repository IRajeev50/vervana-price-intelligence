"""National FPO directory (SFAC) - the all-commodities supplier source.

SFAC (Small Farmers' Agribusiness Consortium, under the Ministry of Agriculture)
publishes a state-wise directory of Farmer Producer Organisations with FPO name,
address, contact and major crops. This is the honest "all commodities" source: a
single official directory whose crops map to onion, potato, tomato, paddy(rice),
wheat, cotton, pulses and more - so a buyer choosing almost any priced commodity
sees real producers to contact.

The PDF is an 11-column table whose flowing text is unusable (columns interleave),
so extraction is done by TABLE CELL via pdfplumber - the FPO Name, Contact and
Major Crops come out as clean cells. `parse_sfac_rows` is pure (it takes already
-extracted rows) and unit-tested without a PDF; only crops that map to a priced
canonical commodity are kept, so nothing surfaces under a commodity we can't
price, and no name/number is invented - every row carries the SFAC source URL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SFAC_URL = (
    "https://sfacindia.com/PDFs/List-of-FPO%20identified-by-SFAC/Statewise%20list%20of%20FPOs.pdf"
)
SOURCE_NAME = "SFAC - National Farmer Producer Organisation directory"
ORG_TYPE = "Farmer Producer Organisation"

_PHONE = re.compile(r"\b([6-9]\d{9})\b")
_EMAIL = re.compile(r"[\w.\-]+@[\w.\-]+\.\w+")

# Crop as written in the "Major Crops" column -> priced canonical commodity.
# Keys are matched against a punctuation-stripped, lower-cased crop token, longest
# key first (so "greengram" wins over "gram").
CROP_TO_COMMODITY: dict[str, str] = {
    "paddy": "Rice",
    "rice": "Rice",
    "wheat": "Wheat",
    "onion": "Onion",
    "potato": "Potato",
    "tomato": "Tomato",
    "cauliflower": "Cauliflower",
    "cabbage": "Cabbage",
    "brinjal": "Brinjal",
    "banana": "Banana",
    "mango": "Mango",
    "cotton": "Cotton",
    "maize": "Maize",
    "turmeric": "Turmeric",
    "redchilli": "Dry Chillies",
    "chilli": "Dry Chillies",
    "chillies": "Dry Chillies",
    "chilly": "Dry Chillies",
    "ginger": "Ginger",
    "blackpepper": "Black pepper",
    "pepper": "Black pepper",
    "groundnut": "Groundnut",
    "soyabean": "Soyabean",
    "soybean": "Soyabean",
    "redgram": "Arhar (Tur/Red Gram)(Whole)",
    "arhar": "Arhar (Tur/Red Gram)(Whole)",
    "tur": "Arhar (Tur/Red Gram)(Whole)",
    "bengalgram": "Bengal Gram(Gram)(Whole)",
    "greengram": "Green Gram (Moong)(Whole)",
    "moong": "Green Gram (Moong)(Whole)",
    "blackgram": "Black Gram (Urd Beans)(Whole)",
    "sugarcane": "Sugarcane",
    "bajra": "Bajra(Pearl Millet/Cumbu)",
    "jowar": "Jowar(Sorghum)",
    "sorghum": "Jowar(Sorghum)",
    "ragi": "Ragi (Finger Millet)",
    "mustard": "Mustard",
    "sesamum": "Sesamum(Sesame,Gingelly,Til)",
    "sesame": "Sesamum(Sesame,Gingelly,Til)",
    "coconut": "Coconut",
    "arecanut": "Arecanut(Betelnut/Supari)",
    "garlic": "Garlic",
    "coffee": "Coffee",
    "rubber": "Rubber",
    "cashew": "Cashewnuts",
    "guava": "Guava",
    "papaya": "Papaya",
    "carrot": "Carrot",
}
_CROP_KEYS = sorted(CROP_TO_COMMODITY, key=len, reverse=True)
# Lines that are a role/label, not the contact's name (honorifics like Shri/Mr
# are kept - they prefix the actual name we want).
_DESIG = re.compile(r"^(Ph|Mob|Cell|Contact|Director|Chairman|CEO|Manager|M\.?\s?No)\b", re.I)


@dataclass
class SfacRecord:
    name: str
    state: str | None
    address: str | None
    contact_name: str | None
    phone: str | None
    email: str | None
    commodities: list[str] = field(default_factory=list)


def _clean(cell: str | None) -> str:
    return re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()


def _map_crops(text: str) -> list[str]:
    found: set[str] = set()
    for token in re.split(r"[,\n;/&]| and ", text or ""):
        norm = re.sub(r"[^a-z]", "", token.lower())
        if not norm:
            continue
        for key in _CROP_KEYS:
            if key in norm:
                found.add(CROP_TO_COMMODITY[key])
                break
    return sorted(found)


def parse_sfac_rows(rows: list[list[str | None]]) -> list[SfacRecord]:
    """Parse extracted 11-column table rows into one record per FPO.

    Columns: 0 S.No, 1 State, 4 FPO Name, 8 Address, 9 Contact, 10 Major Crops.
    Rows without a numeric serial, an FPO name, or a mapped crop are skipped.
    """
    out: list[SfacRecord] = []
    for r in rows:
        if len(r) < 11 or not (r[0] or "").strip().isdigit():
            continue
        name = _clean(r[4])
        if not name:
            continue
        commodities = _map_crops(_clean(r[10]))
        if not commodities:
            continue
        state = re.sub(r"\s*\(.*\)\s*$", "", _clean(r[1])).strip() or None
        contact_cell = r[9] or ""
        phones = _PHONE.findall(contact_cell)
        emails = _EMAIL.findall(contact_cell)
        contact_name = None
        for ln in contact_cell.splitlines():
            ln = ln.strip(" .,-")
            if ln and not _PHONE.search(ln) and not _EMAIL.search(ln) and not _DESIG.match(ln):
                contact_name = ln[:120]
                break
        out.append(
            SfacRecord(
                name=name[:160],
                state=state,
                address=_clean(r[8]) or None,
                contact_name=contact_name,
                phone=phones[0] if phones else None,
                email=emails[0] if emails else None,
                commodities=commodities,
            )
        )
    return out


def extract_table_rows(pdf_bytes: bytes) -> list[list[str | None]]:
    import io
    import logging

    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    import pdfplumber

    rows: list[list[str | None]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                rows.extend(table)
    return rows


def fetch_pdf(url: str = SFAC_URL) -> bytes:
    import httpx

    resp = httpx.get(url, timeout=180.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def build_supplier_records(
    *, url: str = SFAC_URL, pdf_bytes: bytes | None = None
) -> tuple[list[dict], str]:
    """One supplier-import dict per (FPO x mapped commodity)."""
    if pdf_bytes is None:
        pdf_bytes = fetch_pdf(url)
    fpos = parse_sfac_rows(extract_table_rows(pdf_bytes))
    records: list[dict] = []
    for f in fpos:
        for commodity in f.commodities:
            records.append(
                {
                    "commodity": commodity,
                    "name": f.name,
                    "org_type": ORG_TYPE,
                    "state": f.state,
                    "district": None,
                    "address": f.address,
                    "contact_name": f.contact_name,
                    "phone": f.phone,
                    "email": f.email,
                    "source": SOURCE_NAME,
                    "source_url": url,
                }
            )
    return records, url
