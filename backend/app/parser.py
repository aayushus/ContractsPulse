import hashlib
import fitz  # PyMuPDF
from typing import Tuple
import re
from datetime import datetime

def compute_file_hash(file_bytes: bytes) -> str:
    """
    Computes a SHA-256 hash of the uploaded file to detect duplicates.
    This fulfills BRD User Story 004 (Skip re-analysis).
    """
    return hashlib.sha256(file_bytes).hexdigest()

def normalize_contract_text(text: str) -> str:
    """
    Normalize contract text so logically-identical content hashes the same.
    """
    t = (text or "").strip()
    t = re.sub(r"\r\n?", "\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t

def compute_text_hash(text: str) -> str:
    """
    Hash normalized text with a prefix to avoid collisions with PDF byte hashes.
    """
    norm = normalize_contract_text(text)
    return hashlib.sha256(("text:" + norm).encode("utf-8")).hexdigest()

def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, str]:
    """
    Takes raw PDF bytes and extracts text.
    Returns a tuple of (file_hash, raw_text)
    """
    file_hash = compute_file_hash(file_bytes)
    
    # Open the PDF directly from memory
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    
    text_content = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text_content.append(page.get_text("text"))
        
    doc.close()
    
    full_text = "\n".join(text_content)
    return file_hash, full_text


def _slugify(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # Keep it ascii-ish and filesystem-friendly.
    s = s.replace("&", " and ")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:80]


def extract_contract_metadata(raw_text: str) -> dict:
    """
    Best-effort, deterministic metadata extraction for standardized filenames:
    - contract_date: YYYY-MM-DD if detected
    - company: counterparty-ish name if detected
    - contract_type: e.g. "Professional Services Agreement"
    """
    text = (raw_text or "").strip()
    head = text[:4000]

    # Contract type: look for an all-caps title line containing AGREEMENT/CONTRACT/NDA/etc.
    contract_type = None
    for line in head.splitlines():
        l = line.strip()
        if len(l) < 8 or len(l) > 120:
            continue
        if not re.search(r"\b(AGREEMENT|CONTRACT|NDA|ADDENDUM|SOW|STATEMENT OF WORK)\b", l, flags=re.I):
            continue
        if sum(1 for ch in l if ch.isalpha() and ch.isupper()) >= 6:
            contract_type = re.sub(r"\s{2,}", " ", l.title()).strip()
            break

    # Company: attempt to parse "by and between <X>, ... and <Y>, ..."
    company = None
    m = re.search(r"by and between\s+(.{3,200}?)\s*,\s*hereinafter", head, flags=re.I | re.S)
    if m:
        company = re.sub(r"\s+", " ", m.group(1)).strip()
    if company:
        # Drop obvious legal suffix noise.
        company = re.sub(r"^(the\s+)", "", company, flags=re.I).strip()

    # Date: try to find an explicit date like "May 17, 2026" or "05/17/2026".
    contract_date = None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", head)
    if m:
        mm, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yy < 100:
            yy += 2000
        try:
            contract_date = datetime(yy, mm, dd).date().isoformat()
        except Exception:
            contract_date = None
    if not contract_date:
        m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})\b", head, flags=re.I)
        if m:
            try:
                d = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
                contract_date = d.isoformat()
            except Exception:
                contract_date = None

    # Expiry date: scan the full text (not just head) for explicit expiry language.
    expiry_date = None
    expiry_patterns = [
        r"(?:shall\s+)?(?:expire|terminate|end|expir)\s+(?:on|as\s+of)\s+((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})",
        r"(?:valid\s+until|effective\s+until|agreement\s+ends?|term\s+ends?)\s*:?\s*((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})",
        r"(?:expiration\s+date|termination\s+date)\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(?:term\s+of|initial\s+term)[^.]{0,80}(\d{1,2}/\d{1,2}/\d{2,4})",
    ]
    for pat in expiry_patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            raw_d = m.group(1).strip().replace(",", "")
            for fmt in ["%B %d %Y", "%m/%d/%Y", "%m/%d/%y"]:
                try:
                    expiry_date = datetime.strptime(raw_d, fmt).date().isoformat()
                    break
                except Exception:
                    continue
            if expiry_date:
                break

    # Renewal notice days: e.g. "30 days prior to renewal" or "60 days before expiration".
    renewal_notice_days = None
    m = re.search(
        r"(\d{1,3})\s+(?:calendar\s+)?days?\s+(?:prior\s+to|before|in\s+advance\s+of)\s+(?:the\s+)?(?:renewal|expir|terminat)",
        text, flags=re.I
    )
    if m:
        try:
            renewal_notice_days = int(m.group(1))
        except Exception:
            renewal_notice_days = None

    # Contract term duration: e.g. "for a period of 12 months" / "initial term of one (1) year".
    contract_term = None
    m = re.search(
        r"(?:initial\s+term|term\s+of|for\s+a\s+period\s+of|period\s+of)\s+(?:one\s+\(1\)|two\s+\(2\)|three\s+\(3\)|four\s+\(4\)|five\s+\(5\)|1|2|3|4|5|6|12|18|24|36)\s*(year|month)",
        text, flags=re.I
    )
    if m:
        contract_term = m.group(0).strip()

    return {
        "contract_date": contract_date,
        "company": company,
        "contract_type": contract_type,
        "expiry_date": expiry_date,
        "renewal_notice_days": renewal_notice_days,
        "contract_term": contract_term,
    }


def standardized_filename(metadata: dict, default_date: str) -> str:
    """
    Build: YYYY-MM-DD__company__contract-type.pdf, with safe fallbacks.
    """
    contract_date = metadata.get("contract_date") or default_date
    company = _slugify(metadata.get("company") or "unknown-company")
    ctype = _slugify(metadata.get("contract_type") or "contract")
    return f"{contract_date}__{company}__{ctype}.pdf"
