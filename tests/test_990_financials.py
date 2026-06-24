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
