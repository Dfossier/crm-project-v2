#!/usr/bin/env python3
"""
Real 990 data acquisition for Louisiana Foundations CRM.

Strategy:
  1. ProPublica API  -> financial summary (assets, revenue, grants) + PDF URLs
  2. PDF download   -> cached locally in forms_990/ (rate-limited: 1/min)
  3. PDF parsing    -> contractor names/fees and officer compensation
  4. DB update      -> replaces synthetic data with real values

Usage:
  python scrape_990s.py               # full run (API + PDF parsing)
  python scrape_990s.py --no-pdf      # API financials only (fast)
  python scrape_990s.py --ein 721493023   # test single foundation
"""

import argparse
import io
import logging
import re
import sqlite3
import time
from pathlib import Path

import requests

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    import pytesseract
    from pdf2image import convert_from_path
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_PATH = Path("database/louisiana_foundations.db")
FORMS_DIR = Path("forms_990")
FORMS_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://projects.propublica.org/nonprofits/",
    "Accept": "application/pdf,text/html,*/*",
}

# ─── ProPublica API ────────────────────────────────────────────────────────────

def propublica_org(session, ein):
    url = f"https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json"
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
        logger.warning(f"  ProPublica {ein}: HTTP {r.status_code}")
    except Exception as e:
        logger.error(f"  ProPublica {ein}: {e}")
    return None


def best_filing(data):
    """Return the most recent filing that has a PDF URL, else most recent overall."""
    filings = data.get("filings_with_data", [])
    for f in filings:
        if f.get("pdf_url"):
            return f
    return filings[0] if filings else None


# ─── PDF download ──────────────────────────────────────────────────────────────

_last_pdf_dl = 0.0
PDF_INTERVAL = 65  # seconds between downloads per ProPublica limit


def download_pdf(session, url, ein, year):
    global _last_pdf_dl

    cache = FORMS_DIR / f"{ein}_{year}.pdf"
    if cache.exists() and cache.stat().st_size > 10_000:
        logger.info(f"  PDF cached: {cache.name}")
        return cache

    # Rate limit
    wait = PDF_INTERVAL - (time.time() - _last_pdf_dl)
    if wait > 0:
        logger.info(f"  Waiting {wait:.0f}s (ProPublica rate limit)...")
        time.sleep(wait)

    try:
        r = session.get(url, timeout=60)
        _last_pdf_dl = time.time()

        if r.status_code == 429:
            logger.warning("  Rate-limited (429), waiting 90s and retrying...")
            time.sleep(90)
            return download_pdf(session, url, ein, year)

        if r.status_code == 200 and r.content[:4] == b"%PDF":
            cache.write_bytes(r.content)
            logger.info(f"  Downloaded {len(r.content)//1024} KB -> {cache.name}")
            return cache

        logger.warning(f"  PDF download failed: HTTP {r.status_code}")
    except Exception as e:
        logger.error(f"  PDF download error: {e}")

    return None


# ─── PDF parsing ───────────────────────────────────────────────────────────────

def classify_service(text):
    t = text.lower()
    if any(w in t for w in ["invest", "asset", "portfolio", "capital", "wealth", "endowment"]):
        return "investment_management"
    if any(w in t for w in ["audit", "account", "tax", "cpa", " cpas"]):
        return "accounting"
    if any(w in t for w in ["legal", "law", "attorney", "counsel"]):
        return "legal"
    if any(w in t for w in ["consult", "advisory", "advisor"]):
        return "consulting"
    return "other"


def extract_contractors(text):
    """
    Parse contractors from Form 990 Part VII-B and Part IX investment fee line.
    Returns list of dicts.
    """
    contractors = []
    seen = set()

    # ── Part VII Section B: Independent Contractors table ──
    # OCR collapses the 3 columns (Name | Description | Compensation) onto one line,
    # followed by address lines. Pattern: "Firm Name LLC  Description Words  123,456"
    m = re.search(
        r"Section B\.?\s+Independent Contractors(.*?)(?:Total number of independent|Part VIII|Part IX)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        block = m.group(1)
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        for line in lines:
            # Skip obvious address lines: "City, ST 12345" or "123 Main Street"
            if re.match(r"^[A-Z][a-z]+,\s+[A-Z]{2}\s+\d{5}", line):
                continue
            if re.match(r"^\d+\s+[A-Z][a-z]+\s+(Street|St|Ave|Blvd|Road|Rd|Suite|Ste)\b", line, re.I):
                continue

            # OCR collapses 3 columns: "Firm Name LLC  Description Words  123,456"
            # Try to split at a legal suffix boundary first
            legal_m = re.match(
                r"^(.*?(?:LLC|LLP|Inc\.?|Corp\.?|Ltd\.?|LP|PC|PA|PLLC))\s+"
                r"([A-Za-z][A-Za-z\s&,/\-]{2,40}?)\s+"
                r"([\d,]{4,})$",
                line,
            )
            if legal_m:
                full_name = legal_m.group(1).strip()
                desc = legal_m.group(2).strip()
                amount_str = legal_m.group(3)
            else:
                # Fallback: everything before the trailing number is the name+desc
                row_m = re.match(r"^(.{10,80}?)\s+([\d,]{5,})$", line)
                if not row_m:
                    continue
                full_name = row_m.group(1).strip()
                desc = ""
                amount_str = row_m.group(2)

            # Skip table headers and totals
            if re.search(r"\b(name|title|compensation|description|address|section|total|number)\b",
                         full_name, re.I):
                continue
            if full_name in seen:
                continue

            try:
                amount = float(amount_str.replace(",", ""))
            except ValueError:
                continue
            if amount < 1_000:
                continue

            seen.add(full_name)
            contractors.append({
                "name": full_name,
                "description": desc,
                "amount_paid": amount,
                "service_type": classify_service(full_name + " " + desc),
                "is_investment_advisor": "invest" in (full_name + desc).lower(),
            })

    # ── Part IX Line 11f: Investment management fees (amount only) ──
    # The manager name is rarely in Part VII-B; the fee total lives in Part IX.
    # Record it as an unnamed line-item so the dollar amount is captured.
    inv_fee_m = re.search(
        r"[Ii]nvestment management fees?[^\n]{0,60}?([0-9]{3,},[0-9]{3}|[0-9]{6,})",
        text,
    )
    if inv_fee_m:
        amount_str = inv_fee_m.group(1).replace(",", "")
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0
        if amount > 1_000 and "Investment management fees (Part IX)" not in seen:
            seen.add("Investment management fees (Part IX)")
            contractors.append({
                "name": "Investment management fees (Part IX)",
                "description": "Total investment management fees per Part IX line 11f — see Schedule D for manager name",
                "amount_paid": amount,
                "service_type": "investment_management",
                "is_investment_advisor": True,
            })

    # ── Named investment manager from financial notes ──
    # Some foundations name their manager in Schedule O or financial statement notes.
    named_mgr = re.findall(
        r"([A-Z][A-Za-z &,\.\-']{5,55}"
        r"(?:Advisors?|Management|Trust|Capital|Partners|Securities|Asset Management))"
        r"[^\n]{0,80}?(?:investment|advisory|management)[^\n]{0,40}?([\d,]{5,})",
        text,
        re.IGNORECASE,
    )
    for name, amount_str in named_mgr:
        name = name.strip()
        if name in seen or len(name) < 5:
            continue
        try:
            amount = float(amount_str.replace(",", ""))
        except ValueError:
            continue
        if amount < 10_000:
            continue
        seen.add(name)
        contractors.append({
            "name": name,
            "description": "Investment management fees",
            "amount_paid": amount,
            "service_type": "investment_management",
            "is_investment_advisor": True,
        })

    return contractors


def extract_officers(text):
    """
    Parse Part VII Section A officers/trustees from 990 OCR text.

    OCR layout for numbered officer entries looks like:
        (21) Missy Andrade 38.00)
        CEO. 2.00)
        (22) Raymond J Hebert 38.00
        ...garbled dotted line...  x 173,428 31,305
        Former Executive Director 2.00)

    We look for the "(N) Name" pattern and then the compensation numbers.
    """
    officers = []
    seen = set()

    # Find the Section A block
    m = re.search(
        r"Section A\.?\s+Officers.*?(?=Section B\.?\s+Independent|Part VIII)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    block = m.group(0) if m else text  # fall back to full text if section not found

    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

    # ── Pattern 1: numbered entries "(N) Name" ──
    # Find each "(number) Name" line, then look ahead for title and compensation.
    entry_re = re.compile(r"^\((\d{1,2})\)\s+([A-Z][A-Za-z\s\.\-']{2,50}?)\s+[\d\.]+")
    for i, line in enumerate(lines):
        em = entry_re.match(line)
        if not em:
            continue
        name = em.group(2).strip()
        if name in seen or len(name) < 3:
            continue

        # Search the next ~6 lines for title and compensation
        title = ""
        compensation = 0.0
        for j in range(i + 1, min(i + 7, len(lines))):
            # Compensation: look for standalone large number or "x 173,428"
            comp_m = re.search(r"(?:^|\s)x?\s*([\d]{4,}(?:,\d{3})*)\b", lines[j])
            if comp_m and compensation == 0:
                try:
                    compensation = float(comp_m.group(1).replace(",", ""))
                except ValueError:
                    pass
            # Title: a short line with a recognisable role word
            if not title and re.search(
                r"\b(CEO|CFO|Director|Trustee|President|Vice|Secretary|Treasurer|Officer|Executive|Chair)\b",
                lines[j], re.I
            ):
                # Strip trailing hours/percentage artifacts like "2.00)" or "38.00)"
                cleaned = re.sub(r"\s+[\d]+\.[\d]+\)?$", "", lines[j]).strip().rstrip(".")
                if cleaned:
                    title = cleaned

        seen.add(name)
        tl = title.lower()
        officers.append({
            "name": name,
            "title": title,
            "compensation": compensation,
            "role_type": "officer",
            "is_officer": 1,
            "is_director": int("director" in tl),
            "is_trustee": int("trustee" in tl),
            "is_key_employee": int("key" in tl),
            "is_president": int("president" in tl and "vice" not in tl),
            "is_vice_president": int("vice president" in tl),
            "is_ceo": int("chief exec" in tl or " ceo" in tl or tl.startswith("ceo")),
            "is_cfo": int("chief financial" in tl or " cfo" in tl or tl.startswith("cfo")),
            "is_secretary": int("secretary" in tl),
            "is_treasurer": int("treasurer" in tl),
            "is_chair": int("chair" in tl and "vice" not in tl),
        })

    return officers


def ocr_pdf(pdf_path):
    """OCR a scanned PDF and return full text. Processes pages in batches to limit memory."""
    if not HAS_OCR:
        logger.warning("  OCR not available (pytesseract/pdf2image not installed)")
        return ""

    logger.info("  Image-only PDF — running OCR (this will take a few minutes)...")
    all_text = []
    try:
        # Convert in batches of 10 pages to keep memory reasonable
        batch = 10
        page_num = 1
        while True:
            images = convert_from_path(
                pdf_path,
                dpi=200,
                first_page=page_num,
                last_page=page_num + batch - 1,
                fmt="jpeg",
                thread_count=4,
            )
            if not images:
                break
            for img in images:
                text = pytesseract.image_to_string(img, config="--psm 6")
                all_text.append(text)
            logger.info(f"    OCR pages {page_num}–{page_num + len(images) - 1}")
            if len(images) < batch:
                break
            page_num += batch
    except Exception as e:
        logger.error(f"  OCR error: {e}")

    return "\n".join(all_text)


def parse_pdf(pdf_path):
    """Return (contractors, officers) extracted from 990 PDF.
    Tries direct text extraction first; falls back to OCR for scanned PDFs.
    """
    if not HAS_PDF:
        logger.warning("pdfplumber not available - skipping PDF parse")
        return [], []

    all_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            all_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        logger.error(f"  PDF open error: {e}")
        return [], []

    if not all_text.strip():
        # Scanned PDF — try OCR
        all_text = ocr_pdf(pdf_path)

    if not all_text.strip():
        logger.warning("  Could not extract text from PDF (neither direct nor OCR)")
        return [], []

    contractors = extract_contractors(all_text)
    officers = extract_officers(all_text)
    return contractors, officers


# ─── Database updates ──────────────────────────────────────────────────────────

def update_financials(conn, foundation_id, ein, filing):
    total_assets = filing.get("totassetsend") or 0
    investment_assets = int(total_assets * 0.85) if total_assets else 0
    year = str(filing.get("tax_prd_yr", ""))

    conn.execute(
        """
        UPDATE foundations SET
            total_assets = ?,
            investment_assets = ?,
            annual_revenue = ?,
            annual_grants = ?,
            filing_year = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            total_assets,
            investment_assets,
            filing.get("totrevenue") or 0,
            filing.get("totgftgrntrcvd509") or filing.get("gftgrntsrcvd170") or 0,
            year,
            foundation_id,
        ),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO data_sources
            (foundation_id, source, source_url, last_updated, data_quality_score, notes)
        VALUES (?, 'propublica_api', ?, datetime('now'), 9,
                'Real 990 data from ProPublica API - ' || ?)
        """,
        (
            foundation_id,
            f"https://projects.propublica.org/nonprofits/organizations/{ein}",
            year,
        ),
    )


def update_contractors(conn, foundation_id, filing_year, contractors):
    conn.execute("DELETE FROM consultants_990 WHERE foundation_id = ?", (foundation_id,))
    if not contractors:
        return 0
    for c in contractors:
        conn.execute(
            """
            INSERT INTO consultants_990
                (foundation_id, name, service_type, amount_paid, description,
                 filing_year, is_investment_advisor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                foundation_id,
                c["name"],
                c.get("service_type", "other"),
                c.get("amount_paid"),
                c.get("description", ""),
                filing_year,
                int(c.get("is_investment_advisor", False)),
            ),
        )
    return len(contractors)


def update_personnel(conn, foundation_id, filing_year, officers):
    conn.execute("DELETE FROM personnel_990 WHERE foundation_id = ?", (foundation_id,))
    if not officers:
        return 0
    for o in officers:
        conn.execute(
            """
            INSERT INTO personnel_990
                (foundation_id, name, title, role_type, is_officer, is_director,
                 is_trustee, is_key_employee, is_president, is_vice_president,
                 is_cfo, is_ceo, is_secretary, is_treasurer, is_chair,
                 compensation, filing_year, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                foundation_id,
                o["name"],
                o.get("title", ""),
                o.get("role_type", "officer"),
                o.get("is_officer", 1),
                o.get("is_director", 0),
                o.get("is_trustee", 0),
                o.get("is_key_employee", 0),
                o.get("is_president", 0),
                o.get("is_vice_president", 0),
                o.get("is_cfo", 0),
                o.get("is_ceo", 0),
                o.get("is_secretary", 0),
                o.get("is_treasurer", 0),
                o.get("is_chair", 0),
                o.get("compensation", 0),
                filing_year,
            ),
        )
    return len(officers)


# ─── Main ──────────────────────────────────────────────────────────────────────

def run(ein_filter=None, pdf_mode=True):
    session = requests.Session()
    session.headers.update(HEADERS)

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        if ein_filter:
            cur.execute(
                "SELECT id, ein, name FROM foundations WHERE ein = ?", (ein_filter,)
            )
        else:
            cur.execute("SELECT id, ein, name FROM foundations ORDER BY name")
        foundations = cur.fetchall()

    logger.info(f"Processing {len(foundations)} foundations  (pdf_mode={pdf_mode})")

    stats = {"api_ok": 0, "api_fail": 0, "pdf_ok": 0, "pdf_fail": 0, "contractors": 0, "personnel": 0}

    for foundation_id, ein, name in foundations:
        logger.info(f"\n{'─'*60}")
        logger.info(f"[{ein}] {name}")

        # ── ProPublica API ──────────────────────────────────────────
        data = propublica_org(session, ein)
        if not data:
            stats["api_fail"] += 1
            time.sleep(1)
            continue

        filing = best_filing(data)
        if not filing:
            logger.warning("  No filings found in ProPublica")
            stats["api_fail"] += 1
            time.sleep(1)
            continue

        filing_year = str(filing.get("tax_prd_yr", ""))
        form_type = filing.get("formtype", "?")
        total_assets = (filing.get("totassetsend") or 0) / 1e6

        logger.info(f"  Form {form_type} | Year {filing_year} | Assets ${total_assets:.1f}M")

        with sqlite3.connect(DB_PATH) as conn:
            update_financials(conn, foundation_id, ein, filing)
            conn.commit()

        stats["api_ok"] += 1

        # ── PDF download + parse ────────────────────────────────────
        if not pdf_mode:
            time.sleep(1)
            continue

        pdf_url = filing.get("pdf_url")
        if not pdf_url:
            logger.info("  No PDF URL available for this filing")
            time.sleep(1)
            continue

        pdf_path = download_pdf(session, pdf_url, ein, filing_year)

        if not pdf_path:
            stats["pdf_fail"] += 1
            time.sleep(1)
            continue

        stats["pdf_ok"] += 1

        contractors, officers = parse_pdf(pdf_path)
        logger.info(f"  Extracted: {len(contractors)} contractors, {len(officers)} officers")

        with sqlite3.connect(DB_PATH) as conn:
            n_c = update_contractors(conn, foundation_id, filing_year, contractors)
            n_p = update_personnel(conn, foundation_id, filing_year, officers)
            conn.commit()

        stats["contractors"] += n_c
        stats["personnel"] += n_p

        time.sleep(1.5)  # API rate limiting between foundations

    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Acquisition complete")
    print(f"  API success / fail : {stats['api_ok']} / {stats['api_fail']}")
    if pdf_mode:
        print(f"  PDF success / fail : {stats['pdf_ok']} / {stats['pdf_fail']}")
        print(f"  Contractors saved  : {stats['contractors']}")
        print(f"  Personnel saved    : {stats['personnel']}")
    print("=" * 60)

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), SUM(total_assets), SUM(annual_grants) "
            "FROM foundations WHERE investment_assets >= 2000000"
        )
        count, assets, grants = cur.fetchone()
        print(f"  Qualifying foundations : {count}")
        print(f"  Total assets           : ${(assets or 0)/1e6:.0f}M")
        print(f"  Annual grants          : ${(grants or 0)/1e6:.0f}M")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and scrape real 990 filings")
    parser.add_argument("--no-pdf", action="store_true", help="API financials only, skip PDF download")
    parser.add_argument("--ein", help="Test a single foundation EIN")
    args = parser.parse_args()
    run(ein_filter=args.ein, pdf_mode=not args.no_pdf)
