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
    assert d['investment_assets'] == 46_000_000.0  # sum of 3 investment lines: 40M+5M+1M
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
