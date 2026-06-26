# 990 Financial History Ingestion & Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract real financial data from IRS 990/990PF XML filings (2020–2024) for all 41 Louisiana foundations, store it in the database, and add a per-foundation Financial History tab and a cross-foundation Financial Comparison page to the CRM.

**Architecture:** Shared IRS fetch/batch/RemoteZip utilities are extracted to `_990_common.py` so both the existing personnel ingest and the new financial ingest can import them. `ingest_990_financials.py` parses financial fields from the same XML files in a separate run and populates `financial_history` and `investment_details`. Two new UI surfaces are added to `src/crm_app.py`: a Financial History tab on the detail page and a Financial Comparison sidebar page.

**Tech Stack:** Python 3.12, SQLite3, remotezip, defusedxml, Streamlit, Plotly

## Global Constraints

- All file paths relative to `/home/dfoss/.openclaw/workspace/louisiana-foundations-crm/`
- Run all scripts from that directory with the venv active: `source venv/bin/activate`
- Run tests with: `python -m pytest tests/ -v`
- IRS XML namespace constant: `IRS_NS = 'http://www.irs.gov/efile'`
- DB path: `database/louisiana_foundations.db`
- Never download or store XML files to disk; always stream via RemoteZip
- `financial_history` UNIQUE constraint is `(foundation_id, filing_year)` — use `INSERT OR REPLACE`
- `investment_details` has no UNIQUE constraint — clear table before repopulating
- Target years: 2020, 2021, 2022, 2023, 2024 (index format: 2024 uses `XML_BATCH_ID` column; 2020–2023 do not — use ZIP central directory scan for those)
- **Never use `xml.etree.ElementTree` directly** — always use `defusedxml.ElementTree` (protects against XXE and billion-laughs attacks from untrusted XML sources). Add `defusedxml>=0.7.1` to `requirements.txt` and install it before running any ingest.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `_990_common.py` | **Create** | Shared IRS fetch/batch/RemoteZip utilities |
| `ingest_990_xml.py` | **Modify** | Import from `_990_common` instead of defining locally |
| `ingest_990_financials.py` | **Create** | Financial extraction script |
| `tests/test_990_financials.py` | **Create** | Unit tests for parsers and DB functions |
| `src/crm_app.py` | **Modify** | Financial History tab + Financial Comparison page |

---

## Task 1: Extract `_990_common.py`

**Files:**
- Create: `_990_common.py`
- Modify: `ingest_990_xml.py`

**Interfaces:**
- Produces: `IRS_NS`, `BASE_URL`, `INDEX_URL`, `ZIP_URL`, `TARGET_TYPES`, `fetch_index(year, target_eins) -> list[dict]`, `get_batch_names(year) -> list[str]`, `build_batch_map(year, object_ids) -> dict[str, str]`, `_t(el, tag) -> str`, `_yn(val) -> bool`

- [ ] **Step 1: Add `defusedxml` to requirements and install it**

```bash
echo "defusedxml>=0.7.1" >> requirements.txt
pip install defusedxml
```

- [ ] **Step 2: Create `_990_common.py`**

```python
#!/usr/bin/env python3
"""Shared IRS 990 bulk-ZIP fetch utilities used by both ingest scripts."""

import csv
import io
import logging
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

try:
    from remotezip import RemoteZip
except ImportError:
    raise SystemExit("remotezip not installed — run: pip3 install remotezip")

IRS_NS       = 'http://www.irs.gov/efile'
BASE_URL     = "https://apps.irs.gov/pub/epostcard/990/xml"
INDEX_URL    = BASE_URL + "/{year}/index_{year}.csv"
ZIP_URL      = BASE_URL + "/{year}/{batch}.zip"
TARGET_TYPES = {'990', '990PF'}

log = logging.getLogger(__name__)


def fetch_index(year: int, target_eins: set) -> list:
    """Download IRS index CSV for year; return rows matching target EINs and form types."""
    url = INDEX_URL.format(year=year)
    log.info(f"Fetching index: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'IRS-990-Ingest/1.0'})
    with urllib.request.urlopen(req, timeout=90) as r:
        content = r.read().decode('utf-8', errors='replace')
    reader = csv.DictReader(io.StringIO(content))
    return [row for row in reader
            if row['EIN'] in target_eins and row['RETURN_TYPE'] in TARGET_TYPES]


def has_batch_id_column(year: int, target_eins: set) -> bool:
    """Return True if the index CSV for this year has an XML_BATCH_ID column."""
    rows = fetch_index(year, target_eins)
    return bool(rows) and 'XML_BATCH_ID' in rows[0]


def get_batch_names(year: int) -> list:
    """Return expected batch ZIP base-names for years that lack XML_BATCH_ID (2020–2023)."""
    # Pattern: {YEAR}_TEOS_XML_01A .. 12A
    return [f"{year}_TEOS_XML_{i:02d}A" for i in range(1, 13)]


def build_batch_map(year: int, object_ids: list) -> dict:
    """
    Scan ZIP central directories to find which batch contains each OBJECT_ID.
    Used for 2020–2023 where the index lacks XML_BATCH_ID.
    Returns dict: object_id -> batch_name
    """
    target_files = {f"{oid}_public.xml" for oid in object_ids}
    result = {}
    for batch in get_batch_names(year):
        if not target_files:
            break
        zip_url = ZIP_URL.format(year=year, batch=batch)
        log.info(f"  Scanning {batch} central directory...")
        try:
            with RemoteZip(zip_url) as rz:
                for name in rz.namelist():
                    basename = name.split('/')[-1]
                    if basename in target_files:
                        oid = basename.replace('_public.xml', '')
                        result[oid] = batch
                        target_files.discard(basename)
                        log.info(f"    Found {oid} in {batch}")
        except Exception as e:
            log.warning(f"  Could not scan {batch}: {e}")
        time.sleep(0.2)
    if target_files:
        missing = [f.replace('_public.xml', '') for f in target_files]
        log.warning(f"  Not found in any {year} batch: {missing}")
    return result


def deduplicate_index_rows(rows: list) -> dict:
    """
    Given index rows for multiple EINs, keep the most recent period per EIN;
    prefer 990 over 990PF when periods are equal.
    Returns dict: EIN -> row
    """
    best = {}
    for r in rows:
        ein    = r['EIN']
        period = r['TAX_PERIOD']
        if ein not in best or period > best[ein]['TAX_PERIOD']:
            best[ein] = r
        elif period == best[ein]['TAX_PERIOD'] and r['RETURN_TYPE'] == '990':
            best[ein] = r
    return best


def _t(el, tag: str) -> str:
    """Find a direct child by local name and return its text (empty string if absent)."""
    child = el.find(f'{{{IRS_NS}}}{tag}')
    return (child.text or '').strip() if child is not None else ''


def _yn(val) -> bool:
    return str(val).upper() in ('TRUE', 'YES', '1', 'X')


def open_xml_from_batch(zip_url: str, batch: str, obj_id: str) -> bytes | None:
    """
    Open a single XML file from a remote batch ZIP.
    Returns raw bytes or None if the file is not found.
    """
    zip_path = f"{batch}/{obj_id}_public.xml"
    try:
        with RemoteZip(zip_url) as rz:
            return rz.read(zip_path)
    except KeyError:
        log.warning(f"  {zip_path} not found in ZIP")
        return None
    except Exception as e:
        log.warning(f"  Error reading {zip_path}: {e}")
        return None
```

- [ ] **Step 3: Update `ingest_990_xml.py` to import from `_990_common`**

Replace `import xml.etree.ElementTree as ET` with `import defusedxml.ElementTree as ET`. Then replace the block of constants and utility functions (lines 28–158 of `ingest_990_xml.py`) with:

```python
import defusedxml.ElementTree as ET
from _990_common import (
    IRS_NS, BASE_URL, INDEX_URL, ZIP_URL, TARGET_TYPES,
    fetch_index, get_batch_names, build_batch_map,
    deduplicate_index_rows, _t, _yn,
)
```

Then update internal call sites:
- `get_2023_batches()` → `get_batch_names(2023)`
- `build_2023_batch_map(obj_ids)` → `build_batch_map(2023, obj_ids)`

Keep `DB_PATH` defined in `ingest_990_xml.py` (it's script-specific).

- [ ] **Step 4: Verify existing personnel ingest still imports cleanly**

```bash
cd /home/dfoss/.openclaw/workspace/louisiana-foundations-crm
source venv/bin/activate
python -c "import ingest_990_xml; print('OK')"
```

Expected output: `OK` (no errors)

- [ ] **Step 5: Commit**

```bash
git add _990_common.py ingest_990_xml.py requirements.txt
git commit -m "refactor: extract shared IRS fetch utilities into _990_common.py; add defusedxml"
```

---

## Task 2: Schema migration

**Files:**
- Create: `ingest_990_financials.py` (initial skeleton with migration only)
- Test: `tests/test_990_financials.py`

**Interfaces:**
- Produces: `migrate_schema(conn: sqlite3.Connection) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_990_financials.py`:

```python
import sqlite3
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest_990_financials import migrate_schema


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(':memory:')
    conn.execute("""
        CREATE TABLE financial_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            foundation_id INTEGER,
            filing_year INTEGER,
            total_assets REAL,
            investment_assets REAL,
            total_revenue REAL,
            total_expenses REAL,
            grants_paid REAL,
            administrative_expenses REAL,
            fundraising_expenses REAL,
            net_assets_change REAL,
            UNIQUE(foundation_id, filing_year)
        )
    """)
    conn.execute("""
        CREATE TABLE investment_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            foundation_id INTEGER,
            filing_year INTEGER,
            securities_publicly_traded REAL,
            capital_gains REAL
        )
    """)
    conn.execute("INSERT INTO investment_details (foundation_id, filing_year, capital_gains) VALUES (1, 2022, 999.0)")
    conn.commit()
    return conn


def test_migrate_adds_new_columns(mem_db):
    migrate_schema(mem_db)
    cols = {r[1] for r in mem_db.execute("PRAGMA table_info(financial_history)").fetchall()}
    for expected in ('contributions_received', 'investment_income', 'capital_gains_losses',
                     'total_liabilities', 'net_assets_eoy', 'program_service_revenue'):
        assert expected in cols, f"Missing column: {expected}"


def test_migrate_clears_investment_details(mem_db):
    migrate_schema(mem_db)
    count = mem_db.execute("SELECT COUNT(*) FROM investment_details").fetchone()[0]
    assert count == 0


def test_migrate_is_idempotent(mem_db):
    migrate_schema(mem_db)
    migrate_schema(mem_db)  # second call must not raise
    cols = {r[1] for r in mem_db.execute("PRAGMA table_info(financial_history)").fetchall()}
    assert 'contributions_received' in cols
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_990_financials.py::test_migrate_adds_new_columns -v
```

Expected: `ModuleNotFoundError: No module named 'ingest_990_financials'`

- [ ] **Step 3: Create `ingest_990_financials.py` with `migrate_schema`**

```python
#!/usr/bin/env python3
"""
Ingest real financial data from IRS 990/990PF XML filings (2020–2024).
Populates financial_history and investment_details with actual filed values.
"""

import sqlite3
import logging
import time
import defusedxml.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from _990_common import (
    IRS_NS, ZIP_URL, TARGET_TYPES,
    fetch_index, get_batch_names, build_batch_map,
    deduplicate_index_rows, _t,
)

DB_PATH = Path(__file__).parent / "database/louisiana_foundations.db"
LOG_PATH = Path(__file__).parent / "logs/financial_coverage.txt"
TARGET_YEARS = [2020, 2021, 2022, 2023, 2024]
# 2024 index has XML_BATCH_ID; 2020–2023 require central-directory scanning
BATCH_ID_YEARS = {2024}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

NEW_FH_COLUMNS = [
    ('contributions_received', 'REAL'),
    ('investment_income',      'REAL'),
    ('capital_gains_losses',   'REAL'),
    ('total_liabilities',      'REAL'),
    ('net_assets_eoy',         'REAL'),
    ('program_service_revenue','REAL'),
]


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Add new columns to financial_history and clear synthetic investment_details."""
    cur = conn.cursor()
    existing = {r[1] for r in cur.execute("PRAGMA table_info(financial_history)").fetchall()}
    for col, col_type in NEW_FH_COLUMNS:
        if col not in existing:
            cur.execute(f"ALTER TABLE financial_history ADD COLUMN {col} {col_type}")
    cur.execute("DELETE FROM investment_details")
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_990_financials.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add ingest_990_financials.py tests/test_990_financials.py
git commit -m "feat: schema migration for financial_history new columns"
```

---

## Task 3: Financial XML parsers

**Files:**
- Modify: `ingest_990_financials.py`
- Modify: `tests/test_990_financials.py`

**Interfaces:**
- Consumes: `_t(el, tag)` from `_990_common`
- Produces:
  - `parse_990_financials(xml_bytes: bytes) -> dict` — keys: `total_revenue`, `contributions_received`, `program_service_revenue`, `investment_income`, `capital_gains_losses`, `total_expenses`, `grants_paid`, `administrative_expenses`, `fundraising_expenses`, `total_assets`, `total_liabilities`, `net_assets_eoy`, `investment_assets`, `securities_publicly_traded`, `securities_other`, `program_related_investments`
  - `parse_990pf_financials(xml_bytes: bytes) -> dict` — same keys (unused keys are `None`)

- [ ] **Step 1: Write failing parser tests**

Append to `tests/test_990_financials.py`:

```python
from ingest_990_financials import parse_990_financials, parse_990pf_financials

MINIMAL_990_XML = b"""<?xml version="1.0"?>
<Return xmlns="http://www.irs.gov/efile">
  <ReturnData>
    <IRS990>
      <TotalRevenueAmt>5000000</TotalRevenueAmt>
      <CYContributionsGrantsAmt>3000000</CYContributionsGrantsAmt>
      <CYProgramServiceRevenueAmt>500000</CYProgramServiceRevenueAmt>
      <CYInvestmentIncomeAmt>400000</CYInvestmentIncomeAmt>
      <NetGainLossFromSalesOfAssetsAmt>200000</NetGainLossFromSalesOfAssetsAmt>
      <CYTotalExpensesAmt>4000000</CYTotalExpensesAmt>
      <CYGrantsAndSimilarAmountsPaidAmt>3500000</CYGrantsAndSimilarAmountsPaidAmt>
      <CYMgmtAndGeneralExpensesAmt>300000</CYMgmtAndGeneralExpensesAmt>
      <CYFundraisingExpensesAmt>100000</CYFundraisingExpensesAmt>
      <TotalAssetsEOYAmt>50000000</TotalAssetsEOYAmt>
      <TotalLiabilitiesEOYAmt>2000000</TotalLiabilitiesEOYAmt>
      <NetAssetsOrFundBalancesEOYAmt>48000000</NetAssetsOrFundBalancesEOYAmt>
      <InvestmentsPubliclyTradedSecAmt>40000000</InvestmentsPubliclyTradedSecAmt>
      <InvestmentsOtherSecuritiesAmt>5000000</InvestmentsOtherSecuritiesAmt>
      <InvestmentsProgramRelatedAmt>1000000</InvestmentsProgramRelatedAmt>
    </IRS990>
  </ReturnData>
</Return>"""

MINIMAL_990PF_XML = b"""<?xml version="1.0"?>
<Return xmlns="http://www.irs.gov/efile">
  <ReturnData>
    <IRS990PF>
      <TotContriPaidAmt>1000000</TotContriPaidAmt>
      <DividendsAmt>300000</DividendsAmt>
      <InterestAmt>100000</InterestAmt>
      <NetGainLossCapitalAmt>500000</NetGainLossCapitalAmt>
      <TotalRevAndExpnssAmt>1900000</TotalRevAndExpnssAmt>
      <TotalExpensesPFAmt>800000</TotalExpensesPFAmt>
      <QualifyingDistributionsAmt>700000</QualifyingDistributionsAmt>
      <TotAssetsEOYAmt>20000000</TotAssetsEOYAmt>
      <TotLiabilitiesEOYAmt>500000</TotLiabilitiesEOYAmt>
      <TotNetAstOrFundBalancesEOYAmt>19500000</TotNetAstOrFundBalancesEOYAmt>
      <InvstmntSecEOYAmt>18000000</InvstmntSecEOYAmt>
    </IRS990PF>
  </ReturnData>
</Return>"""


def test_parse_990_financials_revenue():
    d = parse_990_financials(MINIMAL_990_XML)
    assert d['total_revenue'] == 5_000_000.0
    assert d['contributions_received'] == 3_000_000.0
    assert d['program_service_revenue'] == 500_000.0
    assert d['investment_income'] == 400_000.0
    assert d['capital_gains_losses'] == 200_000.0


def test_parse_990_financials_expenses():
    d = parse_990_financials(MINIMAL_990_XML)
    assert d['total_expenses'] == 4_000_000.0
    assert d['grants_paid'] == 3_500_000.0
    assert d['administrative_expenses'] == 300_000.0
    assert d['fundraising_expenses'] == 100_000.0


def test_parse_990_financials_balance_sheet():
    d = parse_990_financials(MINIMAL_990_XML)
    assert d['total_assets'] == 50_000_000.0
    assert d['total_liabilities'] == 2_000_000.0
    assert d['net_assets_eoy'] == 48_000_000.0
    assert d['investment_assets'] == 45_000_000.0  # sum of 3 investment lines
    assert d['securities_publicly_traded'] == 40_000_000.0
    assert d['securities_other'] == 5_000_000.0
    assert d['program_related_investments'] == 1_000_000.0


def test_parse_990_financials_bad_xml_returns_none():
    result = parse_990_financials(b"not xml")
    assert result is None


def test_parse_990pf_financials_revenue():
    d = parse_990pf_financials(MINIMAL_990PF_XML)
    assert d['contributions_received'] == 1_000_000.0
    assert d['investment_income'] == 400_000.0        # dividends + interest
    assert d['capital_gains_losses'] == 500_000.0
    assert d['grants_paid'] == 700_000.0


def test_parse_990pf_financials_balance_sheet():
    d = parse_990pf_financials(MINIMAL_990PF_XML)
    assert d['total_assets'] == 20_000_000.0
    assert d['total_liabilities'] == 500_000.0
    assert d['net_assets_eoy'] == 19_500_000.0
    assert d['investment_assets'] == 18_000_000.0
    assert d['securities_publicly_traded'] == 18_000_000.0


def test_parse_990pf_financials_bad_xml_returns_none():
    result = parse_990pf_financials(b"<broken")
    assert result is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_990_financials.py -k "parse" -v
```

Expected: `ImportError` or `AttributeError` on missing functions

- [ ] **Step 3: Implement `parse_990_financials` and `parse_990pf_financials`**

Add to `ingest_990_financials.py` after `migrate_schema`:

```python
def _amt(el, *tags) -> float | None:
    """Try each tag in order; return float value of first match, or None."""
    for tag in tags:
        val = _t(el, tag)
        if val:
            try:
                return float(val)
            except ValueError:
                pass
    return None


def parse_990_financials(xml_bytes: bytes) -> dict | None:
    """Parse financial fields from a Form 990 XML filing. Returns None on parse error."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log.warning(f"XML parse error: {e}")
        return None

    ns = IRS_NS
    body = root.find(f'{{{ns}}}ReturnData/{{{ns}}}IRS990')
    if body is None:
        log.warning("IRS990 element not found in XML")
        return None

    pub_traded = _amt(body, 'InvestmentsPubliclyTradedSecAmt') or 0.0
    other_sec  = _amt(body, 'InvestmentsOtherSecuritiesAmt') or 0.0
    prog_rel   = _amt(body, 'InvestmentsProgramRelatedAmt') or 0.0

    return {
        'total_revenue':           _amt(body, 'TotalRevenueAmt'),
        'contributions_received':  _amt(body, 'CYContributionsGrantsAmt', 'ContriGiftsGrantsEtc'),
        'program_service_revenue': _amt(body, 'CYProgramServiceRevenueAmt'),
        'investment_income':       _amt(body, 'CYInvestmentIncomeAmt'),
        'capital_gains_losses':    _amt(body, 'NetGainLossFromSalesOfAssetsAmt'),
        'total_expenses':          _amt(body, 'CYTotalExpensesAmt', 'TotalFunctionalExpensesAmt'),
        'grants_paid':             _amt(body, 'CYGrantsAndSimilarAmountsPaidAmt'),
        'administrative_expenses': _amt(body, 'CYMgmtAndGeneralExpensesAmt'),
        'fundraising_expenses':    _amt(body, 'CYFundraisingExpensesAmt'),
        'total_assets':            _amt(body, 'TotalAssetsEOYAmt'),
        'total_liabilities':       _amt(body, 'TotalLiabilitiesEOYAmt'),
        'net_assets_eoy':          _amt(body, 'NetAssetsOrFundBalancesEOYAmt'),
        'investment_assets':       pub_traded + other_sec + prog_rel,
        'securities_publicly_traded': pub_traded,
        'securities_other':           other_sec,
        'program_related_investments': prog_rel,
    }


def parse_990pf_financials(xml_bytes: bytes) -> dict | None:
    """Parse financial fields from a Form 990PF XML filing. Returns None on parse error."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log.warning(f"XML parse error: {e}")
        return None

    ns = IRS_NS
    body = root.find(f'{{{ns}}}ReturnData/{{{ns}}}IRS990PF')
    if body is None:
        log.warning("IRS990PF element not found in XML")
        return None

    dividends = _amt(body, 'DividendsAmt') or 0.0
    interest   = _amt(body, 'InterestAmt') or 0.0
    inv_sec    = _amt(body, 'InvstmntSecEOYAmt') or 0.0

    return {
        'total_revenue':           _amt(body, 'TotalRevAndExpnssAmt', 'TotalRevenueAndExpensesAmt'),
        'contributions_received':  _amt(body, 'TotContriPaidAmt', 'ContributionsReceivedAmt'),
        'program_service_revenue': None,
        'investment_income':       dividends + interest,
        'capital_gains_losses':    _amt(body, 'NetGainLossCapitalAmt', 'NetSTCapitalGainLossAmt'),
        'total_expenses':          _amt(body, 'TotalExpensesPFAmt'),
        'grants_paid':             _amt(body, 'QualifyingDistributionsAmt'),
        'administrative_expenses': None,
        'fundraising_expenses':    None,
        'total_assets':            _amt(body, 'TotAssetsEOYAmt'),
        'total_liabilities':       _amt(body, 'TotLiabilitiesEOYAmt'),
        'net_assets_eoy':          _amt(body, 'TotNetAstOrFundBalancesEOYAmt'),
        'investment_assets':       inv_sec,
        'securities_publicly_traded': inv_sec,
        'securities_other':           None,
        'program_related_investments': None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_990_financials.py -k "parse" -v
```

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add ingest_990_financials.py tests/test_990_financials.py
git commit -m "feat: add 990 and 990PF financial XML parsers"
```

---

## Task 4: DB insertion functions

**Files:**
- Modify: `ingest_990_financials.py`
- Modify: `tests/test_990_financials.py`

**Interfaces:**
- Consumes: `migrate_schema(conn)`, `parse_990_financials(xml_bytes)`, `parse_990pf_financials(xml_bytes)`
- Produces:
  - `upsert_financial_history(conn, foundation_id: int, filing_year: int, data: dict) -> None`
  - `upsert_investment_details(conn, foundation_id: int, filing_year: int, data: dict) -> None`

- [ ] **Step 1: Write failing DB tests**

Append to `tests/test_990_financials.py`:

```python
from ingest_990_financials import (
    migrate_schema, upsert_financial_history, upsert_investment_details
)


@pytest.fixture
def migrated_db():
    conn = sqlite3.connect(':memory:')
    conn.execute("""
        CREATE TABLE financial_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            foundation_id INTEGER,
            filing_year INTEGER,
            total_assets REAL, investment_assets REAL,
            total_revenue REAL, total_expenses REAL,
            grants_paid REAL, administrative_expenses REAL,
            fundraising_expenses REAL, net_assets_change REAL,
            UNIQUE(foundation_id, filing_year)
        )
    """)
    conn.execute("""
        CREATE TABLE investment_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            foundation_id INTEGER, filing_year INTEGER,
            securities_publicly_traded REAL, securities_other REAL,
            program_related_investments REAL, other_investments REAL,
            dividend_income REAL, interest_income REAL,
            capital_gains REAL, rental_income REAL,
            investment_expenses REAL, net_investment_income REAL,
            investment_policy_exists BOOLEAN, spending_policy_exists BOOLEAN
        )
    """)
    migrate_schema(conn)
    return conn


def test_upsert_financial_history_inserts(migrated_db):
    data = {
        'total_revenue': 5_000_000.0, 'contributions_received': 3_000_000.0,
        'program_service_revenue': 500_000.0, 'investment_income': 400_000.0,
        'capital_gains_losses': 200_000.0, 'total_expenses': 4_000_000.0,
        'grants_paid': 3_500_000.0, 'administrative_expenses': 300_000.0,
        'fundraising_expenses': 100_000.0, 'total_assets': 50_000_000.0,
        'investment_assets': 45_000_000.0, 'total_liabilities': 2_000_000.0,
        'net_assets_eoy': 48_000_000.0,
    }
    upsert_financial_history(migrated_db, 1, 2023, data)
    row = migrated_db.execute(
        "SELECT total_assets, contributions_received FROM financial_history WHERE foundation_id=1 AND filing_year=2023"
    ).fetchone()
    assert row is not None
    assert row[0] == 50_000_000.0
    assert row[1] == 3_000_000.0


def test_upsert_financial_history_replaces_on_conflict(migrated_db):
    data = {'total_assets': 10.0, 'contributions_received': 1.0,
            'program_service_revenue': None, 'investment_income': None,
            'capital_gains_losses': None, 'total_expenses': None,
            'grants_paid': None, 'administrative_expenses': None,
            'fundraising_expenses': None, 'investment_assets': None,
            'total_liabilities': None, 'net_assets_eoy': None, 'total_revenue': None}
    upsert_financial_history(migrated_db, 1, 2022, data)
    data['total_assets'] = 99.0
    upsert_financial_history(migrated_db, 1, 2022, data)
    rows = migrated_db.execute(
        "SELECT COUNT(*), total_assets FROM financial_history WHERE foundation_id=1 AND filing_year=2022"
    ).fetchone()
    assert rows[0] == 1
    assert rows[1] == 99.0


def test_upsert_investment_details_inserts(migrated_db):
    data = {
        'securities_publicly_traded': 40_000_000.0,
        'securities_other': 5_000_000.0,
        'program_related_investments': 1_000_000.0,
        'investment_income': 400_000.0,
        'capital_gains_losses': 200_000.0,
    }
    upsert_investment_details(migrated_db, 1, 2023, data)
    row = migrated_db.execute(
        "SELECT securities_publicly_traded, capital_gains FROM investment_details"
    ).fetchone()
    assert row[0] == 40_000_000.0
    assert row[1] == 200_000.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_990_financials.py -k "upsert" -v
```

Expected: `ImportError` on missing functions

- [ ] **Step 3: Implement the insertion functions**

Add to `ingest_990_financials.py`:

```python
def upsert_financial_history(conn: sqlite3.Connection, foundation_id: int,
                              filing_year: int, data: dict) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO financial_history
            (foundation_id, filing_year,
             total_assets, investment_assets, total_revenue, total_expenses,
             grants_paid, administrative_expenses, fundraising_expenses,
             contributions_received, investment_income, capital_gains_losses,
             total_liabilities, net_assets_eoy, program_service_revenue)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        foundation_id, filing_year,
        data.get('total_assets'),
        data.get('investment_assets'),
        data.get('total_revenue'),
        data.get('total_expenses'),
        data.get('grants_paid'),
        data.get('administrative_expenses'),
        data.get('fundraising_expenses'),
        data.get('contributions_received'),
        data.get('investment_income'),
        data.get('capital_gains_losses'),
        data.get('total_liabilities'),
        data.get('net_assets_eoy'),
        data.get('program_service_revenue'),
    ))
    conn.commit()


def upsert_investment_details(conn: sqlite3.Connection, foundation_id: int,
                               filing_year: int, data: dict) -> None:
    conn.execute("""
        INSERT INTO investment_details
            (foundation_id, filing_year,
             securities_publicly_traded, securities_other,
             program_related_investments, other_investments,
             capital_gains, net_investment_income,
             dividend_income, interest_income)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        foundation_id, filing_year,
        data.get('securities_publicly_traded'),
        data.get('securities_other'),
        data.get('program_related_investments'),
        None,
        data.get('capital_gains_losses'),
        data.get('investment_income'),
        None,  # dividends not separately tracked in 990; available in 990PF via investment_income
        None,
    ))
    conn.commit()
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_990_financials.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add ingest_990_financials.py tests/test_990_financials.py
git commit -m "feat: add financial_history and investment_details upsert functions"
```

---

## Task 5: Main ingest loop and coverage report

**Files:**
- Modify: `ingest_990_financials.py`

**Interfaces:**
- Consumes: all functions from Tasks 2–4, `fetch_index`, `get_batch_names`, `build_batch_map`, `deduplicate_index_rows` from `_990_common`
- Produces: `ingest()` entry point, `logs/financial_coverage.txt`

- [ ] **Step 1: Add `get_foundation_eins` and `process_filing` helper**

Append to `ingest_990_financials.py`:

```python
def get_foundation_eins(conn: sqlite3.Connection) -> dict:
    """Returns {ein: (foundation_id, name)}"""
    cur = conn.cursor()
    cur.execute("SELECT id, ein, name FROM foundations ORDER BY id")
    return {r[1]: (r[0], r[2]) for r in cur.fetchall()}


def process_filing(conn: sqlite3.Connection, ein_map: dict,
                   xml_bytes: bytes, ein: str, form_type: str,
                   filing_year: int) -> bool:
    """Parse financials from xml_bytes and write to DB. Returns True on success."""
    if form_type == '990PF':
        data = parse_990pf_financials(xml_bytes)
    else:
        data = parse_990_financials(xml_bytes)

    if data is None:
        log.warning(f"  No financial data parsed — EIN {ein} {form_type} {filing_year}")
        return False

    foundation_id, fname = ein_map[ein]
    upsert_financial_history(conn, foundation_id, filing_year, data)
    upsert_investment_details(conn, foundation_id, filing_year, data)
    log.info(f"  EIN {ein} {fname}: assets=${data.get('total_assets') or 0:,.0f}")
    return True
```

- [ ] **Step 2: Add `ingest_year_with_batch_id` (for 2024)**

Append to `ingest_990_financials.py`:

```python
def ingest_year_with_batch_id(conn: sqlite3.Connection, ein_map: dict,
                               year: int, target_eins: set,
                               coverage: dict) -> set:
    """Process one year whose index has XML_BATCH_ID column. Returns EINs processed."""
    rows = fetch_index(year, target_eins)
    best = deduplicate_index_rows(rows)
    done = set()

    by_batch = defaultdict(list)
    for r in best.values():
        batch = r.get('XML_BATCH_ID', '').strip().upper()
        if batch:
            by_batch[batch].append(r)

    for batch, filings in sorted(by_batch.items()):
        zip_url = ZIP_URL.format(year=year, batch=batch)
        log.info(f"Opening {batch} ({len(filings)} filing(s))")
        try:
            from remotezip import RemoteZip
            with RemoteZip(zip_url) as rz:
                for f in filings:
                    ein     = f['EIN']
                    obj_id  = f['OBJECT_ID']
                    period  = f['TAX_PERIOD']
                    ftype   = f['RETURN_TYPE']
                    filing_year = int(period[:4]) if period and len(period) >= 4 else year
                    zip_path = f"{batch}/{obj_id}_public.xml"
                    try:
                        xml_bytes = rz.read(zip_path)
                    except KeyError:
                        log.warning(f"  {zip_path} not found in ZIP")
                        coverage[ein][year] = False
                        continue
                    ok = process_filing(conn, ein_map, xml_bytes, ein, ftype, filing_year)
                    coverage[ein][year] = ok
                    if ok:
                        done.add(ein)
                    time.sleep(0.05)
        except Exception as e:
            log.warning(f"  Failed on {batch}: {e}")
    return done
```

- [ ] **Step 3: Add `ingest_year_with_batch_scan` (for 2020–2023)**

Append to `ingest_990_financials.py`:

```python
def ingest_year_with_batch_scan(conn: sqlite3.Connection, ein_map: dict,
                                 year: int, target_eins: set,
                                 coverage: dict) -> set:
    """Process one year using ZIP central-directory scanning. Returns EINs processed."""
    rows = fetch_index(year, target_eins)
    best = deduplicate_index_rows(rows)
    if not best:
        log.info(f"  No matching filings found in {year} index")
        return set()

    log.info(f"  Building {year} batch map ({len(best)} filings)...")
    obj_to_batch = build_batch_map(year, [r['OBJECT_ID'] for r in best.values()])
    done = set()

    by_batch = defaultdict(list)
    for r in best.values():
        batch = obj_to_batch.get(r['OBJECT_ID'])
        if batch:
            by_batch[batch].append(r)
        else:
            ein = r['EIN']
            log.warning(f"  No batch found for EIN {ein} OBJ {r['OBJECT_ID']}")
            coverage[ein][year] = False

    for batch, filings in sorted(by_batch.items()):
        zip_url = ZIP_URL.format(year=year, batch=batch)
        log.info(f"Opening {batch} ({len(filings)} filing(s))")
        try:
            from remotezip import RemoteZip
            with RemoteZip(zip_url) as rz:
                for f in filings:
                    ein     = f['EIN']
                    obj_id  = f['OBJECT_ID']
                    period  = f['TAX_PERIOD']
                    ftype   = f['RETURN_TYPE']
                    filing_year = int(period[:4]) if period and len(period) >= 4 else year
                    zip_path = f"{batch}/{obj_id}_public.xml"
                    try:
                        xml_bytes = rz.read(zip_path)
                    except KeyError:
                        log.warning(f"  {zip_path} not found in ZIP")
                        coverage[ein][year] = False
                        continue
                    ok = process_filing(conn, ein_map, xml_bytes, ein, ftype, filing_year)
                    coverage[ein][year] = ok
                    if ok:
                        done.add(ein)
                    time.sleep(0.05)
        except Exception as e:
            log.warning(f"  Failed on {batch}: {e}")
    return done
```

- [ ] **Step 4: Add `write_coverage_report` and `ingest()` entry point**

Append to `ingest_990_financials.py`:

```python
def write_coverage_report(ein_map: dict, coverage: dict, years: list) -> None:
    LOG_PATH.parent.mkdir(exist_ok=True)
    header = f"{'Foundation':<50} " + "  ".join(str(y) for y in years)
    lines = [header, "-" * len(header)]
    for ein, (_, name) in sorted(ein_map.items(), key=lambda x: x[1][1]):
        year_cols = "   ".join("✓" if coverage.get(ein, {}).get(y) else "-" for y in years)
        lines.append(f"{name[:50]:<50} {year_cols}")
    report = "\n".join(lines)
    print("\n" + report)
    LOG_PATH.write_text(report)
    log.info(f"Coverage report written to {LOG_PATH}")


def ingest() -> None:
    conn     = sqlite3.connect(DB_PATH)
    ein_map  = get_foundation_eins(conn)
    target   = set(ein_map.keys())

    log.info("=== Migrating schema ===")
    migrate_schema(conn)

    # coverage[ein][year] = True/False
    coverage: dict = {ein: {} for ein in target}

    for year in TARGET_YEARS:
        log.info(f"=== Year {year} ===")
        if year in BATCH_ID_YEARS:
            ingest_year_with_batch_id(conn, ein_map, year, target, coverage)
        else:
            ingest_year_with_batch_scan(conn, ein_map, year, target, coverage)

    write_coverage_report(ein_map, coverage, TARGET_YEARS)

    cur = conn.cursor()
    total = cur.execute("SELECT COUNT(*) FROM financial_history").fetchone()[0]
    foundations = cur.execute("SELECT COUNT(DISTINCT foundation_id) FROM financial_history").fetchone()[0]
    conn.close()
    print(f"\nFinancial records written: {total} across {foundations} foundations")


if __name__ == "__main__":
    ingest()
```

- [ ] **Step 5: Dry-run the script (imports only, no network)**

```bash
python -c "import ingest_990_financials; print('imports OK')"
```

Expected: `imports OK`

- [ ] **Step 6: Run the full ingest (network required, ~10–30 min)**

```bash
python ingest_990_financials.py 2>&1 | tee logs/financial_ingest.log
```

Watch for `WARNING` lines. Inspect coverage report at `logs/financial_coverage.txt`.

- [ ] **Step 7: Verify data in DB**

```bash
sqlite3 database/louisiana_foundations.db \
  "SELECT filing_year, COUNT(*), AVG(total_assets) FROM financial_history GROUP BY filing_year ORDER BY filing_year"
```

Expected: rows for multiple years with non-zero averages

- [ ] **Step 8: Commit**

```bash
git add ingest_990_financials.py logs/financial_coverage.txt
git commit -m "feat: complete 990 financial ingest for 2020-2024"
```

---

## Task 6: Financial History tab in `src/crm_app.py`

**Files:**
- Modify: `src/crm_app.py`

**Interfaces:**
- Consumes: `financial_history` and `investment_details` tables (real data from Task 5)
- Produces: `load_financial_history(foundation_id)` method on `FoundationCRM`, `show_financial_history_tab(crm, foundation_id)` function

- [ ] **Step 1: Add `load_financial_history` to `FoundationCRM`**

In `src/crm_app.py`, find the `FoundationCRM` class and add this method after `load_foundation_details`:

```python
def load_financial_history(self, foundation_id: int):
    with self.get_connection() as conn:
        fh = pd.read_sql_query("""
            SELECT filing_year,
                   total_assets, investment_assets, total_revenue,
                   contributions_received, program_service_revenue,
                   investment_income, capital_gains_losses,
                   total_expenses, grants_paid, administrative_expenses,
                   fundraising_expenses, total_liabilities, net_assets_eoy
            FROM financial_history
            WHERE foundation_id = ?
            ORDER BY filing_year
        """, conn, params=(foundation_id,))

        inv = pd.read_sql_query("""
            SELECT filing_year,
                   securities_publicly_traded, securities_other,
                   program_related_investments, capital_gains, net_investment_income
            FROM investment_details
            WHERE foundation_id = ?
            ORDER BY filing_year
        """, conn, params=(foundation_id,))

    return fh, inv
```

- [ ] **Step 2: Add `show_financial_history_tab` function**

Add this function to `src/crm_app.py` before the `main()` function:

```python
def show_financial_history_tab(crm, foundation_id: int):
    import plotly.graph_objects as go

    fh, inv = crm.load_financial_history(foundation_id)
    all_years = list(range(2020, 2025))

    # ── Coverage row ────────────────────────────────────────────────────────
    st.subheader("Data Coverage")
    years_with_data = set(fh['filing_year'].tolist()) if not fh.empty else set()
    missing = [y for y in all_years if y not in years_with_data]

    cols = st.columns(5)
    for i, year in enumerate(all_years):
        with cols[i]:
            if year in years_with_data:
                st.success(f"✓ {year}")
            else:
                st.error(f"✗ {year}")

    if missing:
        st.info(f"No filing data found for: {', '.join(str(y) for y in missing)}. "
                f"These years will show as gaps in the charts below.")

    if fh.empty:
        st.warning("No financial history available for this foundation. "
                   "Run `ingest_990_financials.py` to populate real data.")
        return

    # ── YoY: Assets ─────────────────────────────────────────────────────────
    st.subheader("Assets Over Time")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fh['filing_year'], y=fh['total_assets'],
                             mode='lines+markers', name='Total Assets',
                             connectgaps=False))
    fig.add_trace(go.Scatter(x=fh['filing_year'], y=fh['investment_assets'],
                             mode='lines+markers', name='Investment Assets',
                             connectgaps=False))
    fig.update_layout(yaxis_tickprefix='$', yaxis_tickformat=',.0f',
                      xaxis=dict(tickmode='array', tickvals=all_years),
                      height=300, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Delta row
    if len(fh) >= 2:
        latest = fh.iloc[-1]
        prior  = fh.iloc[-2]
        delta  = latest['total_assets'] - prior['total_assets']
        direction = "▲" if delta >= 0 else "▼"
        st.caption(f"Total Assets {direction} ${abs(delta)/1e6:.1f}M from {int(prior['filing_year'])}")

    # ── YoY: Revenue breakdown ───────────────────────────────────────────────
    st.subheader("Revenue Breakdown")
    fig2 = go.Figure()
    for col, label in [('contributions_received', 'Contributions'),
                        ('investment_income',      'Investment Income'),
                        ('program_service_revenue','Program Service Revenue')]:
        if col in fh.columns:
            fig2.add_trace(go.Scatter(x=fh['filing_year'], y=fh[col],
                                      mode='lines+markers', name=label,
                                      connectgaps=False))
    fig2.update_layout(yaxis_tickprefix='$', yaxis_tickformat=',.0f',
                       xaxis=dict(tickmode='array', tickvals=all_years),
                       height=300, margin=dict(t=20, b=20))
    st.plotly_chart(fig2, use_container_width=True)

    # ── YoY: Capital gains/losses ────────────────────────────────────────────
    st.subheader("Capital Gains / Losses")
    if 'capital_gains_losses' in fh.columns and fh['capital_gains_losses'].notna().any():
        colors = ['#2ecc71' if v >= 0 else '#e74c3c'
                  for v in fh['capital_gains_losses'].fillna(0)]
        fig3 = go.Figure(go.Bar(x=fh['filing_year'], y=fh['capital_gains_losses'],
                                marker_color=colors, name='Capital Gains/Losses'))
        fig3.add_hline(y=0, line_dash='dash', line_color='gray')
        fig3.update_layout(yaxis_tickprefix='$', yaxis_tickformat=',.0f',
                           xaxis=dict(tickmode='array', tickvals=all_years),
                           height=280, margin=dict(t=20, b=20))
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Capital gains/losses data not available.")

    # ── YoY: Grants paid + payout ratio ─────────────────────────────────────
    st.subheader("Grants Paid & Payout Ratio")
    fig4 = go.Figure()
    fig4.add_trace(go.Bar(x=fh['filing_year'], y=fh['grants_paid'],
                          name='Grants Paid', yaxis='y1'))
    payout = (fh['grants_paid'] / fh['total_assets'] * 100).where(fh['total_assets'] > 0)
    fig4.add_trace(go.Scatter(x=fh['filing_year'], y=payout, mode='lines+markers',
                              name='Payout %', yaxis='y2'))
    fig4.update_layout(
        yaxis=dict(tickprefix='$', tickformat=',.0f', title='Grants Paid'),
        yaxis2=dict(ticksuffix='%', overlaying='y', side='right', title='Payout %'),
        xaxis=dict(tickmode='array', tickvals=all_years),
        height=300, margin=dict(t=20, b=20), legend=dict(orientation='h')
    )
    st.plotly_chart(fig4, use_container_width=True)

    # ── Investment breakdown (most recent year) ──────────────────────────────
    if not inv.empty:
        st.subheader(f"Investment Breakdown ({int(inv.iloc[-1]['filing_year'])})")
        latest_inv = inv.iloc[-1]
        breakdown = {
            'Publicly Traded Securities': latest_inv.get('securities_publicly_traded') or 0,
            'Other Securities':           latest_inv.get('securities_other') or 0,
            'Program-Related':            latest_inv.get('program_related_investments') or 0,
        }
        breakdown = {k: v for k, v in breakdown.items() if v > 0}
        if breakdown:
            fig5 = go.Figure(go.Pie(labels=list(breakdown.keys()),
                                    values=list(breakdown.values()),
                                    hole=0.35))
            fig5.update_layout(height=280, margin=dict(t=20, b=20))
            st.plotly_chart(fig5, use_container_width=True)
```

- [ ] **Step 3: Wrap `show_foundation_details` content in tabs**

In `show_foundation_details`, find the line that starts `if details['foundation'] is not None:` and locate where the content begins. Add a tab bar immediately after the foundation selector:

```python
# Replace this block:
#     if details['foundation'] is not None:
#         foundation = details['foundation']
#         # Basic information
#         col1, col2 = st.columns(2)
# With:
if details['foundation'] is not None:
    foundation = details['foundation']
    tab_overview, tab_financial = st.tabs(["📋 Overview", "📈 Financial History"])
    with tab_overview:
        # [ALL EXISTING CONTENT goes here — basic info, personnel, consultants, etc.]
        # Move the entire existing body of the if-block here, indented one level
        pass  # placeholder — see step note
    with tab_financial:
        show_financial_history_tab(crm, foundation_id)
```

**Important:** The `with tab_overview:` block must contain all the existing code currently in `if details['foundation'] is not None:` (the `col1, col2` columns, personnel sections, investment portfolio, consultants, etc.). Move it in, don't delete it.

- [ ] **Step 4: Verify the app runs**

```bash
cd /home/dfoss/.openclaw/workspace/louisiana-foundations-crm
source venv/bin/activate
streamlit run src/crm_app.py --server.port 8501 &
# Open http://localhost:8501, navigate to Foundation Details, verify two tabs appear
# Check a foundation with data: charts should render
# Check a foundation with missing years: ✗ chips and st.info callout should appear
```

- [ ] **Step 5: Commit**

```bash
git add src/crm_app.py
git commit -m "feat: add Financial History tab to foundation detail page"
```

---

## Task 7: Financial Comparison page

**Files:**
- Modify: `src/crm_app.py`

**Interfaces:**
- Consumes: `financial_history` table, `FoundationCRM.get_connection()`
- Produces: `show_financial_comparison(crm)` function, new sidebar page entry

- [ ] **Step 1: Add `load_comparison_data` to `FoundationCRM`**

Add after `load_financial_history`:

```python
def load_comparison_data(self, foundation_ids: list, years: list) -> pd.DataFrame:
    if not foundation_ids or not years:
        return pd.DataFrame()
    placeholders_f = ','.join('?' * len(foundation_ids))
    placeholders_y = ','.join('?' * len(years))
    with self.get_connection() as conn:
        df = pd.read_sql_query(f"""
            SELECT f.name, fh.foundation_id, fh.filing_year,
                   fh.total_assets, fh.investment_assets, fh.total_revenue,
                   fh.contributions_received, fh.investment_income,
                   fh.capital_gains_losses, fh.grants_paid, fh.net_assets_eoy,
                   fh.total_liabilities,
                   CASE WHEN fh.total_assets > 0
                        THEN fh.grants_paid / fh.total_assets * 100
                        ELSE NULL END AS grant_payout_ratio
            FROM financial_history fh
            JOIN foundations f ON f.id = fh.foundation_id
            WHERE fh.foundation_id IN ({placeholders_f})
              AND fh.filing_year IN ({placeholders_y})
            ORDER BY f.name, fh.filing_year
        """, conn, params=foundation_ids + years)
    return df
```

- [ ] **Step 2: Add `show_financial_comparison` function**

Add before `main()`:

```python
COMPARISON_METRICS = {
    'Total Assets':         'total_assets',
    'Investment Assets':    'investment_assets',
    'Capital Gains/Losses': 'capital_gains_losses',
    'Contributions Received': 'contributions_received',
    'Investment Income':    'investment_income',
    'Grants Paid':          'grants_paid',
    'Net Assets':           'net_assets_eoy',
    'Grant Payout Ratio %': 'grant_payout_ratio',
}


def show_financial_comparison(crm):
    import plotly.express as px
    import plotly.graph_objects as go

    st.title("📊 Financial Comparison")

    # ── Sidebar controls ─────────────────────────────────────────────────────
    metric_label = st.sidebar.selectbox("Metric", list(COMPARISON_METRICS.keys()))
    metric_col   = COMPARISON_METRICS[metric_label]

    all_years = list(range(2020, 2025))
    year_range = st.sidebar.select_slider(
        "Year Range", options=all_years, value=(2020, 2024)
    )
    selected_years = list(range(year_range[0], year_range[1] + 1))

    try:
        all_foundations = pd.read_sql_query(
            "SELECT id, name FROM foundations ORDER BY name",
            crm.get_connection()
        )
    except Exception as e:
        st.error(f"Could not load foundations: {e}")
        return

    selected_names = st.sidebar.multiselect(
        "Foundations", options=all_foundations['name'].tolist(),
        default=all_foundations['name'].tolist()
    )
    selected_ids = all_foundations[
        all_foundations['name'].isin(selected_names)
    ]['id'].tolist()

    if not selected_ids:
        st.info("Select at least one foundation.")
        return

    df = crm.load_comparison_data(selected_ids, selected_years)

    # ── Snapshot vs. Trend view ───────────────────────────────────────────────
    is_single_year = len(selected_years) == 1

    if is_single_year:
        year = selected_years[0]
        st.subheader(f"{metric_label} — {year}")

        # Build full roster including foundations with no data
        snapshot = df[df['filing_year'] == year][['name', metric_col]].copy()
        all_names_df = pd.DataFrame({'name': selected_names})
        snapshot = all_names_df.merge(snapshot, on='name', how='left')
        snapshot = snapshot.sort_values(metric_col, ascending=True, na_position='first')

        is_pct = 'ratio' in metric_col or 'pct' in metric_col
        colors = ['#cccccc' if pd.isna(v) else '#2c7bb6' for v in snapshot[metric_col]]
        hover = snapshot[metric_col].apply(
            lambda v: "No data" if pd.isna(v)
            else (f"{v:.1f}%" if is_pct else f"${v:,.0f}")
        )

        fig = go.Figure(go.Bar(
            x=snapshot[metric_col], y=snapshot['name'],
            orientation='h', marker_color=colors,
            hovertext=hover, hoverinfo='text+y'
        ))
        tick_fmt = '.1f' if is_pct else ',.0f'
        tick_prefix = '' if is_pct else '$'
        tick_suffix = '%' if is_pct else ''
        fig.update_layout(
            xaxis=dict(tickformat=tick_fmt, tickprefix=tick_prefix, ticksuffix=tick_suffix),
            height=max(400, len(selected_names) * 22),
            margin=dict(l=200, t=20, b=40)
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.subheader(f"{metric_label} — {selected_years[0]}–{selected_years[-1]}")

        fig = go.Figure()
        for name in selected_names:
            fdata = df[df['name'] == name].sort_values('filing_year')
            n_years = fdata['filing_year'].nunique()
            completeness = f"{n_years}/{len(selected_years)} yrs"
            fig.add_trace(go.Scatter(
                x=fdata['filing_year'], y=fdata[metric_col],
                mode='lines+markers', name=f"{name} ({completeness})",
                connectgaps=False
            ))
        is_pct = 'ratio' in metric_col or 'pct' in metric_col
        fig.update_layout(
            yaxis=dict(
                tickformat='.1f' if is_pct else ',.0f',
                tickprefix='' if is_pct else '$',
                ticksuffix='%' if is_pct else ''
            ),
            xaxis=dict(tickmode='array', tickvals=selected_years),
            height=450, margin=dict(t=20, b=20),
            legend=dict(orientation='v', x=1.01)
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Data table ───────────────────────────────────────────────────────────
    st.subheader("Data Table")
    if df.empty:
        st.info("No data for selected foundations and years.")
    else:
        pivot = df.pivot_table(index='name', columns='filing_year',
                               values=metric_col, aggfunc='first')
        pivot = pivot.reindex(columns=selected_years)
        pivot.columns = [str(y) for y in pivot.columns]
        pivot = pivot.reset_index().rename(columns={'name': 'Foundation'})

        # Format for display
        is_pct = 'ratio' in metric_col or 'pct' in metric_col
        year_cols = [str(y) for y in selected_years]
        display = pivot.copy()
        for col in year_cols:
            display[col] = display[col].apply(
                lambda v: '—' if pd.isna(v)
                else (f"{v:.1f}%" if is_pct else f"${v:,.0f}")
            )
        st.dataframe(display, use_container_width=True, hide_index=True)

        # CSV export (raw numbers)
        csv_bytes = pivot.to_csv(index=False).encode()
        st.download_button(
            label="⬇ Download CSV",
            data=csv_bytes,
            file_name=f"foundation_{metric_col}_comparison.csv",
            mime='text/csv'
        )
```

- [ ] **Step 3: Add the page to the sidebar selectbox**

Find the `page = st.sidebar.selectbox(...)` call in `main()`. Add `"📊 Financial Comparison"` to the options list. Then in the `if/elif` dispatch block below it, add:

```python
elif page == "📊 Financial Comparison":
    show_financial_comparison(crm)
```

- [ ] **Step 4: Verify the comparison page**

```bash
# If streamlit is still running, it will hot-reload.
# Navigate to "📊 Financial Comparison" in the sidebar.
# Verify:
# - Metric dropdown shows all 8 options
# - Year range slider works
# - Single year (drag both ends to same year): bar chart appears, gray bars for no-data foundations
# - Multi-year: line chart appears, legend shows completeness fractions
# - Data table renders with — for missing cells
# - Download CSV button produces a file
```

- [ ] **Step 5: Commit**

```bash
git add src/crm_app.py
git commit -m "feat: add Financial Comparison page to CRM sidebar"
```
