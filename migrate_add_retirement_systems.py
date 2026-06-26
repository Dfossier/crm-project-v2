"""
Migration: add retirement_systems, system_financials, system_personnel tables
and seed with the ~12 Louisiana statewide public retirement systems.

Safe to run multiple times (uses CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE).
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database", "louisiana_foundations.db")


DDL = """
CREATE TABLE IF NOT EXISTS retirement_systems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    abbreviation TEXT,
    system_type TEXT,
    website TEXT,
    phone TEXT,
    address TEXT,
    city TEXT DEFAULT 'Baton Rouge',
    state TEXT DEFAULT 'LA',
    zip_code TEXT,
    executive_director TEXT,
    cio TEXT,
    investment_consultant TEXT,
    actuary TEXT,
    custodian TEXT,
    total_assets REAL,
    funded_ratio REAL,
    active_members INTEGER,
    retired_members INTEGER,
    asset_data_year INTEGER,
    fiscal_year_end TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    total_assets REAL,
    actuarial_liability REAL,
    funded_ratio REAL,
    employer_contributions REAL,
    employee_contributions REAL,
    investment_return_pct REAL,
    benefits_paid REAL,
    active_members INTEGER,
    retired_members INTEGER,
    equity_pct REAL,
    fixed_income_pct REAL,
    alternatives_pct REAL,
    real_estate_pct REAL,
    cash_pct REAL,
    FOREIGN KEY (system_id) REFERENCES retirement_systems(id),
    UNIQUE (system_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS system_personnel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    title TEXT,
    role_type TEXT,
    is_executive_director BOOLEAN DEFAULT 0,
    is_cio BOOLEAN DEFAULT 0,
    is_board_chair BOOLEAN DEFAULT 0,
    phone TEXT,
    email TEXT,
    notes TEXT,
    FOREIGN KEY (system_id) REFERENCES retirement_systems(id),
    UNIQUE (system_id, name, title)
);
"""

# Seed data — (name, abbreviation, system_type, website, phone, city, zip,
#              executive_director, cio, investment_consultant, actuary, custodian,
#              total_assets, funded_ratio, active_members, retired_members,
#              asset_data_year, fiscal_year_end, notes)
SYSTEMS = [
    (
        "Teachers' Retirement System of Louisiana",
        "TRSL",
        "statewide",
        "https://www.trsl.org",
        "(225) 925-6446",
        "Baton Rouge",
        "70821",
        "Dana Vicknair",
        None,
        "Callan LLC",
        "Gabriel, Roeder, Smith & Company",
        "State Street Bank",
        26_500_000_000,
        72.4,
        76_000,
        47_000,
        2024,
        "June 30",
        "Largest Louisiana public pension fund. Covers K-12 and higher-ed teachers.",
    ),
    (
        "Louisiana State Employees' Retirement System",
        "LASERS",
        "statewide",
        "https://lasersonline.org",
        "(225) 922-0600",
        "Baton Rouge",
        "70821",
        "Cindy Rougeou",
        None,
        "Callan LLC",
        "Gabriel, Roeder, Smith & Company",
        "State Street Bank",
        15_000_000_000,
        63.5,
        67_000,
        48_000,
        2024,
        "June 30",
        "Covers most state agency employees. 24 distinct retirement plans.",
    ),
    (
        "Louisiana Sheriffs' Pension and Relief Fund",
        "SPRF",
        "statewide",
        "https://www.lsprf.com",
        "(225) 932-4060",
        "Baton Rouge",
        "70821",
        None,
        None,
        None,
        "Gabriel, Roeder, Smith & Company",
        None,
        4_400_000_000,
        None,
        None,
        None,
        2022,
        "December 31",
        "Covers sheriffs and deputy sheriffs statewide.",
    ),
    (
        "Louisiana School Employees' Retirement System",
        "LSERS",
        "statewide",
        "https://lsers.net",
        "(225) 925-6484",
        "Baton Rouge",
        "70821",
        None,
        None,
        "Verus Advisory",
        "Cavanaugh Macdonald",
        None,
        2_300_000_000,
        None,
        None,
        None,
        2024,
        "June 30",
        "Covers non-certified school employees (bus drivers, custodians, etc.).",
    ),
    (
        "Parochial Employees' Retirement System of Louisiana",
        "PERSLA",
        "parochial",
        "https://persla.org",
        "(225) 928-1361",
        "Baton Rouge",
        "70821",
        None,
        None,
        None,
        "Cavanaugh Macdonald",
        None,
        None,
        None,
        None,
        None,
        None,
        "June 30",
        "Covers employees of parish governing authorities and related entities.",
    ),
    (
        "Municipal Employees' Retirement System of Louisiana",
        "MERS",
        "municipal",
        "https://mersla.com",
        "(225) 219-0500",
        "Baton Rouge",
        "70821",
        None,
        None,
        None,
        "Gabriel, Roeder, Smith & Company",
        None,
        None,
        None,
        None,
        None,
        None,
        "December 31",
        "Covers municipal employees of participating cities and towns.",
    ),
    (
        "Firefighters' Retirement System",
        "FRS",
        "statewide",
        "https://www.frsla.com",
        "(225) 925-4060",
        "Baton Rouge",
        "70821",
        None,
        None,
        None,
        "Gabriel, Roeder, Smith & Company",
        None,
        None,
        None,
        None,
        None,
        None,
        "June 30",
        "Covers municipal firefighters statewide.",
    ),
    (
        "Clerks of Court Retirement and Relief Fund",
        "CERA",
        "specialty",
        None,
        None,
        "Baton Rouge",
        "70821",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "June 30",
        "Covers elected clerks of court and their employees.",
    ),
    (
        "District Attorneys' Retirement System",
        "DSRS",
        "specialty",
        None,
        None,
        "Baton Rouge",
        "70821",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "June 30",
        "Covers elected district attorneys and assistant DAs.",
    ),
    (
        "Assessors' Retirement Fund",
        "ARF",
        "specialty",
        "https://www.louisianaassessors.org/assessors-retirement",
        None,
        "Baton Rouge",
        "70821",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "June 30",
        "Covers elected parish tax assessors and their employees.",
    ),
    (
        "Registrars of Voters Employees' Retirement System",
        "ROVERS",
        "specialty",
        None,
        None,
        "Baton Rouge",
        "70821",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "June 30",
        "Covers registrars of voters and their employees.",
    ),
    (
        "State Police Pension and Retirement System",
        "SLPF",
        "statewide",
        None,
        None,
        "Baton Rouge",
        "70821",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "June 30",
        "Covers Louisiana State Police officers.",
    ),
]

# Known financials: (abbreviation, fiscal_year, total_assets, funded_ratio,
#                    investment_return_pct, active_members, retired_members)
FINANCIALS = [
    ("TRSL", 2024, 26_500_000_000, 72.4, 7.2, 76_000, 47_000),
    ("TRSL", 2023, 26_651_188_968, 71.8, 6.8, 77_000, 46_000),
    ("LASERS", 2024, 15_000_000_000, 63.5, 14.0, 67_000, 48_000),
    ("LASERS", 2023, 14_512_703_270, 62.1, 8.1, 68_000, 47_000),
    ("LSERS", 2024, 2_299_477_320, None, None, None, None),
    ("SPRF", 2022, 4_400_000_000, None, None, None, None),
]


def run():
    con = sqlite3.connect(DB_PATH)

    for stmt in DDL.strip().split(";\n\n"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)

    insert_system = """
        INSERT OR IGNORE INTO retirement_systems
            (name, abbreviation, system_type, website, phone, city, zip_code,
             executive_director, cio, investment_consultant, actuary, custodian,
             total_assets, funded_ratio, active_members, retired_members,
             asset_data_year, fiscal_year_end, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    for row in SYSTEMS:
        con.execute(insert_system, row)

    # Insert known financials (look up system_id by abbreviation)
    for abbr, fy, assets, funded, ret_pct, active, retired in FINANCIALS:
        row = con.execute(
            "SELECT id FROM retirement_systems WHERE abbreviation = ?", [abbr]
        ).fetchone()
        if row:
            con.execute(
                """INSERT OR IGNORE INTO system_financials
                   (system_id, fiscal_year, total_assets, funded_ratio,
                    investment_return_pct, active_members, retired_members)
                   VALUES (?,?,?,?,?,?,?)""",
                [row[0], fy, assets, funded, ret_pct, active, retired],
            )

    con.commit()

    count = con.execute("SELECT COUNT(*) FROM retirement_systems").fetchone()[0]
    fin_count = con.execute("SELECT COUNT(*) FROM system_financials").fetchone()[0]
    print(f"Done: {count} retirement systems, {fin_count} financial records")
    con.close()


if __name__ == "__main__":
    run()
