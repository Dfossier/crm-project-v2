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
TARGET_YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
# 2024+ indexes have XML_BATCH_ID; 2020–2023 require central-directory scanning
BATCH_ID_YEARS = {2024, 2025, 2026}

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

    # Nested group helpers — capital gains, admin, fundraising live inside groups
    def _grp_amt(parent, grp_tag, child_tag):
        grp = parent.find(f'{{{ns}}}{grp_tag}')
        if grp is None:
            return None
        val = _t(grp, child_tag)
        if val:
            try:
                return float(val)
            except ValueError:
                pass
        return None

    # TotalFunctionalExpensesGrp holds the column totals for Part IX
    fx_grp = body.find(f'{{{ns}}}TotalFunctionalExpensesGrp')
    admin_exp      = _amt(fx_grp, 'ManagementAndGeneralAmt') if fx_grp is not None else None
    fundraising    = _amt(fx_grp, 'FundraisingAmt') if fx_grp is not None else None

    # Capital gains: Part VIII NetGainOrLossInvestmentsGrp/TotalRevenueColumnAmt
    cap_gains = _grp_amt(body, 'NetGainOrLossInvestmentsGrp', 'TotalRevenueColumnAmt')

    # Investment securities total from Schedule D
    sched_d = root.find(f'{{{ns}}}ReturnData/{{{ns}}}IRS990ScheduleD')
    inv_total = _amt(sched_d, 'TotalBookValueSecuritiesAmt') if sched_d is not None else None

    return {
        'total_revenue':           _amt(body, 'CYTotalRevenueAmt'),
        'contributions_received':  _amt(body, 'CYContributionsGrantsAmt', 'ContriGiftsGrantsEtc'),
        'program_service_revenue': _amt(body, 'CYProgramServiceRevenueAmt'),
        'investment_income':       _amt(body, 'CYInvestmentIncomeAmt'),
        'capital_gains_losses':    cap_gains,
        'total_expenses':          _amt(body, 'CYTotalExpensesAmt'),
        'grants_paid':             _amt(body, 'CYGrantsAndSimilarPaidAmt'),
        'administrative_expenses': admin_exp,
        'fundraising_expenses':    fundraising,
        'total_assets':            _amt(body, 'TotalAssetsEOYAmt'),
        'total_liabilities':       _amt(body, 'TotalLiabilitiesEOYAmt'),
        'net_assets_eoy':          _amt(body, 'NetAssetsOrFundBalancesEOYAmt'),
        'investment_assets':       inv_total,
        'securities_publicly_traded': inv_total,
        'securities_other':           None,
        'program_related_investments': None,
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

    # 990PF data lives inside named groups, not as direct children
    rev   = body.find(f'{{{ns}}}AnalysisOfRevenueAndExpenses')
    bal   = body.find(f'{{{ns}}}Form990PFBalanceSheetsGrp')
    qdist = body.find(f'{{{ns}}}PFQualifyingDistributionsGrp')

    def _ga(grp, *tags):
        return _amt(grp, *tags) if grp is not None else None

    # Investment assets: sum securities from balance sheet (book value)
    inv_sec = 0.0
    if bal is not None:
        for tag in ('USGovernmentObligationsEOYAmt', 'CorporateStockEOYAmt',
                    'CorporateBondsEOYAmt', 'OtherInvestmentsEOYAmt'):
            inv_sec += _amt(bal, tag) or 0.0
    inv_sec = inv_sec or None

    # Investment income: interest + dividends (gross, from revenue column)
    interest  = _ga(rev, 'InterestOnSavRevAndExpnssAmt') or 0.0
    dividends = _ga(rev, 'DividendsRevAndExpnssAmt') or 0.0
    inv_income = (interest + dividends) or None

    stock = _ga(bal, 'CorporateStockEOYAmt')
    bonds = (_ga(bal, 'CorporateBondsEOYAmt') or 0) + (_ga(bal, 'OtherInvestmentsEOYAmt') or 0)

    return {
        'total_revenue':           _ga(rev, 'TotalRevAndExpnssAmt'),
        'contributions_received':  _ga(rev, 'ContriRcvdRevAndExpnssAmt'),
        'program_service_revenue': None,
        'investment_income':       inv_income,
        'capital_gains_losses':    _ga(rev, 'NetGainSaleAstRevAndExpnssAmt'),
        'total_expenses':          _ga(rev, 'TotalExpensesRevAndExpnssAmt'),
        'grants_paid':             _ga(qdist, 'QualifyingDistributionsAmt'),
        'administrative_expenses': None,
        'fundraising_expenses':    None,
        'total_assets':            _ga(bal, 'TotalAssetsEOYAmt'),
        'total_liabilities':       _ga(bal, 'TotalLiabilitiesEOYAmt'),
        'net_assets_eoy':          _ga(bal, 'TotNetAstOrFundBalancesEOYAmt'),
        'investment_assets':       inv_sec,
        'securities_publicly_traded': stock,
        'securities_other':           bonds or None,
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
                # Detect actual folder prefix:
                # - 2021: "2021Redo_allCycles/{obj}_public.xml"
                # - 2022: "Cycles_.../{obj}_public.xml" or "{batch}/{obj}_public.xml"
                # - 2025+: flat ZIP, "{obj}_public.xml" (no subdirectory)
                first_names = rz.namelist()[:1]
                if not first_names:
                    prefix = batch + '/'
                elif '/' in first_names[0]:
                    prefix = first_names[0].split('/')[0] + '/'
                else:
                    prefix = ''  # flat ZIP
                if prefix not in (batch + '/', ''):
                    log.info(f"  Non-standard ZIP prefix detected: {prefix!r}")
                for f in filings:
                    ein     = f['EIN']
                    obj_id  = f['OBJECT_ID']
                    period  = f['TAX_PERIOD']
                    ftype   = f['RETURN_TYPE']
                    filing_year = int(period[:4]) if period and len(period) >= 4 else year
                    zip_path = f"{prefix}{obj_id}_public.xml"
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
                # Detect actual folder prefix:
                # - 2021: "2021Redo_allCycles/{obj}_public.xml"
                # - 2022: "Cycles_.../{obj}_public.xml" or "{batch}/{obj}_public.xml"
                # - 2025+: flat ZIP, "{obj}_public.xml" (no subdirectory)
                first_names = rz.namelist()[:1]
                if not first_names:
                    prefix = batch + '/'
                elif '/' in first_names[0]:
                    prefix = first_names[0].split('/')[0] + '/'
                else:
                    prefix = ''  # flat ZIP
                if prefix not in (batch + '/', ''):
                    log.info(f"  Non-standard ZIP prefix detected: {prefix!r}")
                for f in filings:
                    ein     = f['EIN']
                    obj_id  = f['OBJECT_ID']
                    period  = f['TAX_PERIOD']
                    ftype   = f['RETURN_TYPE']
                    filing_year = int(period[:4]) if period and len(period) >= 4 else year
                    zip_path = f"{prefix}{obj_id}_public.xml"
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
