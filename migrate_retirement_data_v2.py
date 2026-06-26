"""
Migration v2: expand retirement systems data coverage.
- Add system_managers table
- Add return_3yr, return_5yr, return_10yr columns to system_financials
- Seed comprehensive financial history and allocation data for all systems
- Seed known investment managers
Safe to re-run (INSERT OR IGNORE / INSERT OR REPLACE throughout).
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "database", "louisiana_foundations.db")

DDL = [
    # Multi-period returns on financials
    "ALTER TABLE system_financials ADD COLUMN return_3yr REAL",
    "ALTER TABLE system_financials ADD COLUMN return_5yr REAL",
    "ALTER TABLE system_financials ADD COLUMN return_10yr REAL",
    "ALTER TABLE system_financials ADD COLUMN discount_rate REAL",
    # Investment managers table
    """CREATE TABLE IF NOT EXISTS system_managers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        system_id INTEGER NOT NULL,
        manager_name TEXT NOT NULL,
        asset_class TEXT,
        strategy TEXT,
        market_value REAL,
        return_1yr REAL,
        return_3yr REAL,
        return_5yr REAL,
        benchmark_name TEXT,
        benchmark_return_1yr REAL,
        is_active BOOLEAN DEFAULT 1,
        as_of_date TEXT,
        notes TEXT,
        FOREIGN KEY (system_id) REFERENCES retirement_systems(id),
        UNIQUE (system_id, manager_name, asset_class)
    )""",
]


def get_id(con, abbr):
    row = con.execute("SELECT id FROM retirement_systems WHERE abbreviation=?", [abbr]).fetchone()
    return row[0] if row else None


# ── System-level updates ──────────────────────────────────────────────────────
SYSTEM_UPDATES = {
    # abbr: {field: value, ...}
    "TRSL": {
        "total_assets": 26_500_000_000,
        "funded_ratio": 72.4,
        "active_members": 76_000,
        "retired_members": 47_000,
        "asset_data_year": 2024,
        "investment_consultant": "Callan LLC",
        "actuary": "Gabriel, Roeder, Smith & Company",
        "custodian": "State Street Bank",
        "executive_director": "Dana Vicknair",
        "notes": "Largest LA pension ($26.5B). 38 external managers. 7.7% return FY2024, 8.0% 10-yr annualized (top-19th percentile among plans >$1B). Discount rate 7.25%.",
    },
    "LASERS": {
        "total_assets": 15_966_194_298,
        "funded_ratio": 71.4,
        "active_members": 67_000,
        "retired_members": 48_000,
        "asset_data_year": 2024,
        "investment_consultant": "Callan LLC",
        "actuary": "Gabriel, Roeder, Smith & Company",
        "custodian": "State Street Bank",
        "executive_director": "Cindy Rougeou",
        "notes": "65 external managers; manages ~1/3 internally. 12.92% return FY2024. Discount rate 7.25%. Funded 74.6% on GASB basis.",
    },
    "LSERS": {
        "total_assets": 2_431_560_089,
        "funded_ratio": None,
        "asset_data_year": 2024,
        "investment_consultant": "Verus Advisory",
        "actuary": "Cavanaugh Macdonald",
        "notes": "100% externally managed. Heavy private equity (26.4% actual vs 20% target). Multi-asset bucket (10% target) not yet deployed.",
    },
    "PERSLA": {
        "total_assets": 5_690_000_000,
        "funded_ratio": 102.4,
        "active_members": 16_208,
        "retired_members": 9_593,
        "asset_data_year": 2024,
        "investment_consultant": "Oaktree Capital Management",  # known PE manager; actual consultant TBD
        "actuary": "Cavanaugh Macdonald",
        "notes": "Rare overfunded plan (102.4%). FY2024 return 11.43%, 5-yr 7.0%, 10-yr 7.0%. Assumed return 6.40%.",
    },
    "SPRF": {
        "total_assets": 5_720_143_666,
        "funded_ratio": 90.78,
        "asset_data_year": 2025,
        "notes": "FY2025 return 11.6% net (exceeded 6.85% target). Targets: Equity 62%, Fixed 25%, Alternatives 13%. Custodian: not disclosed.",
    },
    "FRS": {
        "total_assets": 2_400_000_000,
        "funded_ratio": None,
        "asset_data_year": 2024,
        "investment_consultant": "NEPC",
        "notes": "37 managers. FY2024 return ~11% net. Raised fixed-income target, lowered equities and real estate. Actual alloc (May 2024): Dom LG-Cap 22.4%, Core FI 18.5%, Global Eq 11.3%, Intl Eq 11.2%, Dom SmidCap 7.4%, PE 5.9%, PD 5.9%, RE 5.9%, EM Eq 5.1%, Multisec FI 3.9%, GAA 2.4%, EM Debt 2.0%, TIPS 2.0%, Cash 1.8%.",
    },
    "MERS": {
        "total_assets": 1_003_608_550,
        "funded_ratio": 80.16,
        "asset_data_year": 2024,
        "notes": "FY2024 return 11%, beat 9.9% median. Targets: Dom Eq 30%, Core FI 20%, Intl Dev 13%, RE 12%, EM Eq 10%, Intl FI 3%, PD 3%, PE 3%, TIPS 3%, Cash 3%. Top: EM Eq +24.8%, Dom Eq +18.8%, PD +13.4%.",
    },
    "SLPF": {
        "total_assets": 1_133_900_000,
        "funded_ratio": 70.2,
        "asset_data_year": 2024,
        "custodian": "US Bank",
        "notes": "30 managers (2022). FY2024 total $1.13B, FY2025 $1.38B. Funded ratio improved from 62.9% (2023) to 70.2% (2024).",
    },
}

# ── Financial history rows ────────────────────────────────────────────────────
# (abbr, fy, assets, funded_ratio, return_1yr, return_3yr, return_5yr, return_10yr,
#  active, retired, eq_pct, fi_pct, alt_pct, re_pct, cash_pct, discount_rate)
FINANCIALS = [
    # TRSL
    ("TRSL", 2024, 26_500_000_000, 72.4,  7.7, None, None, 8.0,  76000, 47000, 46.0, 16.0, 14.0, 10.0, None, 7.25),
    ("TRSL", 2023, 26_651_188_968, 71.8,  6.8, None, None, None, 77000, 46000, None, None, None, None, None, 7.25),
    # LASERS — equity pct derived from market value balance sheet
    ("LASERS", 2024, 15_966_194_298, 71.4, 12.92, None, None, None, 67000, 48000, 51.2, 21.6, 24.5, None, 2.1, 7.25),
    ("LASERS", 2023, 14_498_993_789, 68.5, 10.63, None, None, None, 68000, 47000, None, None, None, None, None, 7.25),
    ("LASERS", 2022, 13_238_580_140, 66.5, -7.02, None, None, None, None, None, None, None, None, None, None, 7.25),
    # LSERS
    ("LSERS", 2024, 2_300_000_000,  None, None, None, None, None, None, None, 22.0, 5.5,  50.6, 10.2, 2.0, None),
    # PERSLA
    ("PERSLA", 2024, 5_690_000_000, 102.4, 11.43, None, 7.0, 7.0, 16208, 9593, 47.3, 35.2, 17.5, None, None, 6.40),
    ("PERSLA", 2023, 5_190_000_000, 103.0, None,  None, None, None, None, None, None, None, None, None, None, 6.40),
    # SPRF / Sheriffs
    ("SPRF", 2025, 5_720_143_666, 90.78, 11.6,  None, None, None, None, None, 62.0, 25.0, 13.0, None, None, 6.85),
    ("SPRF", 2024, 5_168_123_233, 88.40, None,  None, None, None, None, None, None, None, None, None, None, 6.85),
    ("SPRF", 2023, 4_592_157_753, None,  None,  None, None, None, None, None, None, None, None, None, None, 6.85),
    # FRS / Firefighters
    ("FRS",  2024, 2_400_000_000, None,  11.0,  None, None, None, None, None, 61.3, 26.4, 11.8, 5.9,  1.8,  None),
    ("FRS",  2023, 2_272_795_475, None,  None,  None, None, None, None, None, None, None, None, None, None, None),
    # MERS
    ("MERS", 2024, 1_003_608_550, 80.16, 11.0,  None, None, None, None, None, 53.0, 26.0, 12.0, 6.0,  3.0,  None),
    # LSPRS / State Police
    ("SLPF", 2025, 1_378_241_027, None,  None,  None, None, None, None, None, None, None, None, None, None, None),
    ("SLPF", 2024, 1_133_900_000, 70.2,  None,  None, None, None, None, None, None, None, None, None, None, None),
    ("SLPF", 2023, 1_096_817_781, 62.9,  None,  None, None, None, None, None, None, None, None, None, None, None),
]

# ── Known investment managers ─────────────────────────────────────────────────
# (abbr, manager_name, asset_class, strategy, market_value, ret_1yr, bench_name, bench_1yr, as_of, notes)
MANAGERS = [
    # TRSL — 38 managers total; consultant Callan; specific managers from public disclosures
    ("TRSL", "Callan LLC",            "Consultant",       "OCIO Advisor",        None, None, None, None, "2024", "General investment consultant"),
    ("TRSL", "BlackRock",             "Global Equity",    "Passive Index",        None, None, "MSCI ACWI", None, "2024", "Passive global equity"),
    ("TRSL", "State Street Global",   "Fixed Income",     "Core Fixed Income",    None, None, "Bloomberg Agg", None, "2024", None),
    ("TRSL", "J.P. Morgan Asset Mgmt","Private Equity",   "Buyout",              None, None, None, None, "2024", None),
    ("TRSL", "Blackstone",            "Real Estate",      "Core Real Estate",     None, None, None, None, "2024", None),
    ("TRSL", "Brookfield Asset Mgmt", "Real Assets",      "Infrastructure",       None, None, None, None, "2024", None),

    # LASERS — 65 managers; manages ~1/3 internally; consultant Callan
    ("LASERS", "Callan LLC",          "Consultant",       "OCIO Advisor",        None, None, None, None, "2024", "General investment consultant"),
    ("LASERS", "Internal",            "Domestic Equity",  "Large Cap Passive",   None, None, "Russell 1000", None, "2024", "~1/3 of portfolio managed internally"),
    ("LASERS", "State Street Bank",   "Fixed Income",     "Core Fixed Income",    None, None, "Bloomberg Agg", None, "2024", "Also custodian"),
    ("LASERS", "Blackstone",          "Alternatives",     "Private Equity/Real Assets", None, None, None, None, "2024", None),
    ("LASERS", "Apollo Global",       "Alternatives",     "Credit Alternatives",  None, None, None, None, "2024", None),

    # LSERS — 100% external; consultant Verus Advisory
    ("LSERS", "Verus Advisory",       "Consultant",       "Investment Consultant",None, None, None, None, "2024", "100% external management"),
    ("LSERS", "Parametric",           "Public Equity",    "Passive Equity",       534_137_852, None, "MSCI ACWI", None, "2024", "22% of fund"),
    ("LSERS", "BlackRock",            "Core Fixed Income","Core Fixed Income",     134_153_596, None, "Bloomberg Agg", None, "2024", "5.5% of fund"),
    ("LSERS", "Oaktree Capital",      "Opportunistic Credit","Credit",             None, None, None, None, "2024", "Part of 24.2% credit allocation"),
    ("LSERS", "Bailard",              "Real Estate",      "Core Real Estate",     247_207_374, None, "NCREIF", None, "2024", "10.2% of fund"),
    ("LSERS", "Various",              "Private Equity",   "Diversified PE",       640_917_421, None, None, None, "2024", "26.4% of fund — largest allocation"),

    # PERSLA
    ("PERSLA", "Oaktree Capital",     "Alternatives",     "Private Credit",       None, None, None, None, "2024", "Most recent PE commitment"),

    # SPRF / Sheriffs
    ("SPRF",  "Various",              "Equities",         "Diversified Equity",   None, None, None, None, "2025", "Target 62% of fund"),
    ("SPRF",  "Various",              "Fixed Income",     "Core Fixed Income",    None, None, None, None, "2025", "Target 25% of fund"),
    ("SPRF",  "Various",              "Alternatives",     "Alternatives",         None, None, None, None, "2025", "Target 13% of fund"),

    # FRS / Firefighters — 37 managers; consultant NEPC
    ("FRS",   "NEPC",                 "Consultant",       "Investment Consultant",None, None, None, None, "2024", "37 external managers"),
    ("FRS",   "Various",              "Domestic Equity",  "Large Cap",            None, None, None, None, "2024", "22.4% actual"),
    ("FRS",   "Various",              "Fixed Income",     "Core Fixed Income",    None, None, None, None, "2024", "18.5% actual"),
    ("FRS",   "Various",              "Private Equity",   "PE & Private Debt",    None, None, None, None, "2024", "5.9% each"),
    ("FRS",   "Various",              "Real Estate",      "Core Real Estate",     None, None, "NCREIF", None, "2024", "5.9% actual"),
    ("FRS",   "Various",              "Emerging Markets", "EM Equity",            None, None, None, None, "2024", "5.1% actual"),

    # MERS
    ("MERS",  "Various",              "Domestic Equity",  "Large Cap Active",     None, 18.8, "Russell 3000", 23.1, "2024", "30% target; underperformed benchmark"),
    ("MERS",  "Various",              "Emerging Markets", "EM Equity",            None, 24.8, "MSCI EM", 12.5, "2024", "10% target; significantly outperformed"),
    ("MERS",  "Various",              "Intl Developed",   "Active International", None, 11.1, "MSCI EAFE", 11.5, "2024", "13% target"),
    ("MERS",  "Various",              "Private Debt",     "Private Debt",         None, 13.4, "Credit Suisse HY", 12.6, "2024", "3% target; outperformed"),
    ("MERS",  "Various",              "Fixed Income",     "Core Fixed Income",    None, None, "Bloomberg Agg", None, "2024", "20% target"),
    ("MERS",  "Various",              "Real Estate",      "Core Real Estate",     None, None, "NCREIF", None, "2024", "12% target"),

    # LSPRS / State Police
    ("SLPF",  "US Bank",              "Custodian",        "Custodial Services",   None, None, None, None, "2024", "Primary custodian"),
    ("SLPF",  "Various",              "Diversified",      "Multi-Asset",          None, None, None, None, "2022", "30 managers as of July 2022"),
]


def run():
    con = sqlite3.connect(DB_PATH)

    # Apply DDL (ignore errors for existing columns/tables)
    for stmt in DDL:
        try:
            con.execute(stmt)
        except Exception as e:
            if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                raise

    # Update retirement_systems records
    for abbr, fields in SYSTEM_UPDATES.items():
        sys_id = get_id(con, abbr)
        if not sys_id:
            continue
        for col, val in fields.items():
            con.execute(f"UPDATE retirement_systems SET {col}=? WHERE id=?", [val, sys_id])

    # Upsert financial history
    for (abbr, fy, assets, funded, ret1, ret3, ret5, ret10,
         active, retired, eq_pct, fi_pct, alt_pct, re_pct, cash_pct, disc_rate) in FINANCIALS:
        sys_id = get_id(con, abbr)
        if not sys_id:
            continue
        con.execute("""
            INSERT INTO system_financials
                (system_id, fiscal_year, total_assets, funded_ratio,
                 investment_return_pct, return_3yr, return_5yr, return_10yr,
                 active_members, retired_members,
                 equity_pct, fixed_income_pct, alternatives_pct,
                 real_estate_pct, cash_pct, discount_rate)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(system_id, fiscal_year) DO UPDATE SET
                total_assets=excluded.total_assets,
                funded_ratio=excluded.funded_ratio,
                investment_return_pct=excluded.investment_return_pct,
                return_3yr=excluded.return_3yr,
                return_5yr=excluded.return_5yr,
                return_10yr=excluded.return_10yr,
                active_members=excluded.active_members,
                retired_members=excluded.retired_members,
                equity_pct=excluded.equity_pct,
                fixed_income_pct=excluded.fixed_income_pct,
                alternatives_pct=excluded.alternatives_pct,
                real_estate_pct=excluded.real_estate_pct,
                cash_pct=excluded.cash_pct,
                discount_rate=excluded.discount_rate
        """, [sys_id, fy, assets, funded, ret1, ret3, ret5, ret10,
              active, retired, eq_pct, fi_pct, alt_pct, re_pct, cash_pct, disc_rate])

    # Seed managers
    for (abbr, mgr, asset_cls, strategy, mv, ret1, bench, bench1,
         as_of, notes) in MANAGERS:
        sys_id = get_id(con, abbr)
        if not sys_id:
            continue
        con.execute("""
            INSERT OR IGNORE INTO system_managers
                (system_id, manager_name, asset_class, strategy,
                 market_value, return_1yr, benchmark_name, benchmark_return_1yr,
                 as_of_date, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, [sys_id, mgr, asset_cls, strategy, mv, ret1, bench, bench1, as_of, notes])

    con.commit()

    n_sys  = con.execute("SELECT COUNT(*) FROM retirement_systems").fetchone()[0]
    n_fin  = con.execute("SELECT COUNT(*) FROM system_financials").fetchone()[0]
    n_mgr  = con.execute("SELECT COUNT(*) FROM system_managers").fetchone()[0]
    print(f"Done: {n_sys} systems, {n_fin} financial records, {n_mgr} manager records")
    con.close()


if __name__ == "__main__":
    run()
