"""Coconut Development Board producer-company directory (official, consent-clean).

The CDB (a Govt of India statutory body) publishes contact details of Coconut
Producer Companies (CPCs) - farmer-producer organisations that list themselves so
buyers can reach them for market linkage. This module fetches that official PDF
and parses it into supplier records. It is the *legitimate* answer to "coconut
suppliers across India, with contacts": an official directory of ORGANISATIONS
(not scraped individuals), imported with provenance - never crawled trader data.

Parsing is deliberately conservative:
  * each contact row is attached to the most-recent CPC header (a serial number
    that resets per state), so a phone is never misfiled onto the wrong company;
  * a CPC with no phone at all is still recorded (name + state), but nothing is
    invented; every record carries the CDB source URL for verification.

`parse_cdb_text` is pure (works on extracted text) and unit-tested without a PDF.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CDB_URL = "https://coconutboard.in/images/CPC/cpc-contactdetails.pdf"
SOURCE_NAME = "Coconut Development Board - Coconut Producer Companies directory"
ORG_TYPE = "Coconut Producer Company"

# States/UTs used as section headers in the directory (upper-case, whole line).
_STATES = {
    "ANDHRA PRADESH",
    "ARUNACHAL PRADESH",
    "ASSAM",
    "BIHAR",
    "CHHATTISGARH",
    "GOA",
    "GUJARAT",
    "HARYANA",
    "HIMACHAL PRADESH",
    "JHARKHAND",
    "KARNATAKA",
    "KERALA",
    "MADHYA PRADESH",
    "MAHARASHTRA",
    "MANIPUR",
    "MEGHALAYA",
    "MIZORAM",
    "NAGALAND",
    "ODISHA",
    "PUNJAB",
    "RAJASTHAN",
    "SIKKIM",
    "TAMIL NADU",
    "TELANGANA",
    "TRIPURA",
    "UTTAR PRADESH",
    "UTTARAKHAND",
    "WEST BENGAL",
    "PUDUCHERRY",
    "ANDAMAN & NICOBAR",
}
_PHONE = re.compile(r"\b([6-9]\d{9})\b")
_EMAIL = re.compile(r"[\w.\-]+@[\w.\-]+\.\w+")


_NAME_END = ("CPC", "CPCL", "COMPANY", "LTD")
_ADDR_HINT = re.compile(r"\d{6}|\bD\.?\s?No\b|\bDoor\b|\bP\.?\s?O\b|\bPost\b|,", re.IGNORECASE)


def _looks_like_address(line: str) -> bool:
    return bool(_ADDR_HINT.search(line))


@dataclass
class CpcRecord:
    name: str
    state: str | None
    address: str = ""
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    _contacts: list[dict] = field(default_factory=list, repr=False)
    _name_open: bool = True


def parse_cdb_text(text: str) -> list[CpcRecord]:
    """Parse extracted CDB PDF text into one record per producer company."""
    out: list[CpcRecord] = []
    cur: CpcRecord | None = None
    state: str | None = None
    expected = 1
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        up = line.upper()
        if up in _STATES:
            # Serials restart per state; a repeated header (same state, new page)
            # must NOT reset the counter or the section's later CPCs are lost.
            if up != state:
                state = up
                expected = 1
            continue
        m = re.match(r"^(\d+)\s+(\S.*)$", line)
        if m and int(m.group(1)) == expected and not _PHONE.search(line):
            if cur is not None:
                out.append(cur)
            nm = m.group(2).strip()
            cur = CpcRecord(name=nm, state=(state.title() if state else None))
            cur._name_open = not nm.upper().endswith(_NAME_END)
            expected += 1
            continue
        if cur is None:
            continue
        ph = _PHONE.search(line)
        em = _EMAIL.search(line)
        if ph or em:
            cur._name_open = False
            name = re.split(r"\d|@", line)[0].strip(" ,.-")
            cur._contacts.append(
                {
                    "name": name or None,
                    "phone": ph.group(1) if ph else None,
                    "email": em.group(0) if em else None,
                }
            )
            continue
        # Name may wrap onto the next line(s), and the address can begin on the same
        # physical line as the name's tail. "CPC" ends the name; then the remainder
        # (and later lines) are the address.
        if cur._name_open and not cur._contacts:
            if "CPC" in up:
                end = up.find("CPC") + 3
                cur.name = f"{cur.name} {line[:end].strip()}".strip()
                rest = line[end:].strip(" ,.-")
                if rest:
                    cur.address = f"{cur.address} {rest}".strip()
                cur._name_open = False
                continue
            if (
                not _looks_like_address(line)
                and len(line.split()) <= 3
                and not re.search(r"\d", line)
            ):
                cur.name = f"{cur.name} {line}".strip()  # short fragment of the name
                continue
            cur._name_open = False  # anything else starts the address
        if not cur._contacts:
            cur.address = f"{cur.address} {line}".strip()
    if cur is not None:
        out.append(cur)

    for c in out:
        # Primary reachable contact: first row with a phone, else first with an email.
        primary = next((x for x in c._contacts if x["phone"]), None) or next(
            (x for x in c._contacts if x["email"]), None
        )
        if primary:
            c.contact_name = primary["name"]
            c.phone = primary["phone"]
            c.email = primary["email"] or next(
                (x["email"] for x in c._contacts if x["email"]), None
            )
    return out


def extract_pdf_text(pdf_bytes: bytes) -> str:
    import io
    import logging

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def fetch_pdf(url: str = CDB_URL) -> bytes:
    import httpx

    resp = httpx.get(url, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def build_supplier_records(
    *, url: str = CDB_URL, pdf_bytes: bytes | None = None
) -> tuple[list[dict], str]:
    """Fetch/parse the CDB directory into supplier-import dicts for Coconut."""
    if pdf_bytes is None:
        pdf_bytes = fetch_pdf(url)
    cpcs = parse_cdb_text(extract_pdf_text(pdf_bytes))
    records = [
        {
            "commodity": "Coconut",
            "name": c.name,
            "org_type": ORG_TYPE,
            "state": c.state,
            "address": c.address or None,
            "contact_name": c.contact_name,
            "phone": c.phone,
            "email": c.email,
            "source": SOURCE_NAME,
            "source_url": url,
        }
        for c in cpcs
        if c.name
    ]
    return records, url
