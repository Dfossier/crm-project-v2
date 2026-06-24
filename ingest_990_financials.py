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
    ('contributions_received',  'REAL'),
    ('investment_income',       'REAL'),
    ('capital_gains_losses',    'REAL'),
    ('total_liabilities',       'REAL'),
    ('net_assets_eoy',          'REAL'),
    ('program_service_revenue', 'REAL'),
]


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Add new columns to financial_history if they are missing."""
    cur = conn.cursor()
    existing = {r[1] for r in cur.execute("PRAGMA table_info(financial_history)").fetchall()}
    for col, col_type in NEW_FH_COLUMNS:
        if col not in existing:
            cur.execute(f"ALTER TABLE financial_history ADD COLUMN {col} {col_type}")
    conn.commit()


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

    cur = conn.cursor()
    cur.execute("DELETE FROM investment_details")
    conn.commit()
    log.info("Cleared investment_details for fresh repopulation")

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
