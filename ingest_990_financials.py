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
    """Add new columns to financial_history and clear synthetic investment_details."""
    cur = conn.cursor()
    existing = {r[1] for r in cur.execute("PRAGMA table_info(financial_history)").fetchall()}
    for col, col_type in NEW_FH_COLUMNS:
        if col not in existing:
            cur.execute(f"ALTER TABLE financial_history ADD COLUMN {col} {col_type}")
    cur.execute("DELETE FROM investment_details")
    conn.commit()
