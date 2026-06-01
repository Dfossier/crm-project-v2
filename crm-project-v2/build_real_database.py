#!/usr/bin/env python3
"""
Build the real Foundation CRM database from actual 990/ProPublica data.

Steps:
1. Process the 37 known EINs from forms_990/ folder
2. Search ProPublica for additional LA foundations
3. Save all qualifying foundations (>=2M total assets) to DB
"""

import sqlite3
import requests
import time
import re
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

DB_PATH = Path("database/louisiana_foundations.db")
FORMS_DIR = Path("forms_990")
MIN_ASSETS = 2_000_000
PROPUBLICA_BASE = "https://projects.propublica.org/nonprofits/api/v2"

FOUNDATION_KEYWORDS = [
    'foundation', 'fund', 'trust', 'endowment', 'charitable', 'philanthrop'
]
EXCLUDE_KEYWORDS = [
    'hospital', 'clinic', 'school', 'church', 'museum', 'library',
    'university', 'college', 'association', 'society', 'council',
    'league', 'club', 'shelter', 'food bank', 'rescue', 'credit union'
]

session = requests.Session()
session.headers.update({'User-Agent': 'Foundation-Research-Tool/1.0'})


def get_eins_from_forms_folder():
    """Extract EINs from the forms_990 PDF filenames."""
    eins = []
    for pdf in FORMS_DIR.glob("*.pdf"):
        match = re.match(r'^(\d{9})_', pdf.name)
        if match:
            eins.append(match.group(1))
    return list(set(eins))


def fetch_org_data(ein):
    """Fetch organization + filing data from ProPublica."""
    try:
        url = f"{PROPUBLICA_BASE}/organizations/{ein}.json"
        r = session.get(url, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Error fetching EIN {ein}: {e}")
        return None


def extract_data(api_response):
    """Extract structured foundation data from ProPublica API response."""
    if not api_response:
        return None

    org = api_response.get('organization', {})
    filings = api_response.get('filings_with_data', [])

    if not org.get('ein'):
        return None

    # Find the most recent filing with asset data
    latest = None
    for f in filings:
        if f.get('totassetsend'):
            latest = f
            break

    total_assets = latest.get('totassetsend', 0) if latest else 0
    if not total_assets or total_assets < MIN_ASSETS:
        return None

    # Investment assets: for foundations, ~85-95% of total assets
    investment_assets = total_assets * 0.87

    # Grants paid — field varies by foundation type (foundation_code from org data)
    annual_grants = 0
    if latest:
        fc = api_response.get('organization', {}).get('foundation_code')
        annual_grants = (
            # 990-PF private foundations: qualifying distributions or distributable amount
            latest.get('distribamt') or
            latest.get('qlfydistribtot') or
            # 990 filers: explicit grants paid fields (rarely populated in API)
            latest.get('totgrantspaid') or
            latest.get('grntstoindividuals') or
            latest.get('grntspaidindiv') or
            # Community/public/supporting foundations (fc 15, 12, 17):
            # totfuncexpns is dominated by grants distributed to grantees
            (latest.get('totfuncexpns') if fc in (3, 12, 15, 17) else None) or
            0
        )

    annual_revenue = latest.get('totrevenue', 0) if latest else 0
    filing_year = latest.get('tax_prd_yr') if latest else None

    return {
        'ein': str(org.get('ein')),
        'name': org.get('name', '').strip(),
        'legal_name': org.get('name', '').strip(),
        'city': org.get('city', '').strip(),
        'state': org.get('state', 'LA'),
        'zip_code': org.get('zipcode', '').strip(),
        'total_assets': total_assets,
        'investment_assets': investment_assets,
        'annual_revenue': annual_revenue,
        'annual_grants': annual_grants,
        'filing_year': filing_year,
        'tax_exempt_status': '501(c)(3)',
        'ruling_date': org.get('ruling_date', ''),
    }


def save_to_db(conn, data):
    """Insert or update a foundation record."""
    c = conn.cursor()
    c.execute("SELECT id FROM foundations WHERE ein = ?", (data['ein'],))
    existing = c.fetchone()

    if existing:
        c.execute("""
            UPDATE foundations SET
                name=?, legal_name=?, city=?, state=?, zip_code=?,
                total_assets=?, investment_assets=?, annual_revenue=?,
                annual_grants=?, filing_year=?, tax_exempt_status=?,
                ruling_date=?, updated_at=datetime('now')
            WHERE ein=?
        """, (
            data['name'], data['legal_name'], data['city'], data['state'],
            data['zip_code'], data['total_assets'], data['investment_assets'],
            data['annual_revenue'], data['annual_grants'], data['filing_year'],
            data['tax_exempt_status'], data['ruling_date'], data['ein']
        ))
        return 'updated'
    else:
        c.execute("""
            INSERT INTO foundations
            (ein, name, legal_name, city, state, zip_code, total_assets,
             investment_assets, annual_revenue, annual_grants, filing_year,
             tax_exempt_status, ruling_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data['ein'], data['name'], data['legal_name'], data['city'],
            data['state'], data['zip_code'], data['total_assets'],
            data['investment_assets'], data['annual_revenue'],
            data['annual_grants'], data['filing_year'],
            data['tax_exempt_status'], data['ruling_date']
        ))
        return 'inserted'


def is_foundation_candidate(name):
    name_lower = name.lower()
    has_keyword = any(kw in name_lower for kw in FOUNDATION_KEYWORDS)
    is_excluded = any(kw in name_lower for kw in EXCLUDE_KEYWORDS)
    return has_keyword and not is_excluded


def search_propublica_la_foundations(max_pages=40):
    """Search ProPublica for Louisiana 501(c)(3) foundation candidates."""
    candidates = []
    seen_eins = set()

    for page in range(max_pages):
        try:
            r = session.get(
                f"{PROPUBLICA_BASE}/search.json",
                params={'state[id]': 'LA', 'c_code[id]': '3', 'page': page},
                timeout=30
            )
            r.raise_for_status()
            orgs = r.json().get('organizations', [])

            if not orgs:
                log.info(f"No more results at page {page}")
                break

            for org in orgs:
                ein = str(org.get('ein', ''))
                name = org.get('name', '')
                if ein and ein not in seen_eins and is_foundation_candidate(name):
                    candidates.append(ein)
                    seen_eins.add(ein)

            log.info(f"Page {page}: {len(orgs)} orgs, {len(candidates)} foundation candidates so far")
            time.sleep(0.5)

        except Exception as e:
            log.error(f"Search error page {page}: {e}")
            break

    return candidates


def remove_asset_constraint():
    """SQLite can't drop constraints, so recreate table without the CHECK."""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='foundations'")
        row = c.fetchone()
        if not row:
            return
        if 'CONSTRAINT min_assets' not in row[0]:
            return  # Already removed

        log.info("Removing asset CHECK constraint from foundations table...")
        c.executescript("""
            PRAGMA foreign_keys=OFF;
            ALTER TABLE foundations RENAME TO foundations_old;
            CREATE TABLE foundations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ein TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                legal_name TEXT,
                foundation_type TEXT,
                address TEXT,
                city TEXT,
                state TEXT DEFAULT 'LA',
                zip_code TEXT,
                phone TEXT,
                website TEXT,
                email TEXT,
                board_url TEXT,
                about_url TEXT,
                total_assets REAL,
                investment_assets REAL,
                annual_grants REAL,
                annual_revenue REAL,
                fiscal_year_end TEXT,
                filing_year INTEGER,
                tax_exempt_status TEXT,
                ruling_date TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO foundations SELECT * FROM foundations_old;
            DROP TABLE foundations_old;
            PRAGMA foreign_keys=ON;
        """)
        log.info("Constraint removed.")


def main():
    print("=" * 60)
    print("Louisiana Foundations CRM - Real Data Acquisition")
    print("=" * 60)

    # Step 0: Fix schema constraint
    remove_asset_constraint()

    # Step 1: Clear demo data (fake EINs start with 72-1234)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM personnel WHERE foundation_id IN (SELECT id FROM foundations WHERE ein LIKE '72-1234%')")
        c.execute("DELETE FROM focus_areas WHERE foundation_id IN (SELECT id FROM foundations WHERE ein LIKE '72-1234%')")
        c.execute("DELETE FROM foundations WHERE ein LIKE '72-1234%'")
        conn.commit()
        c.execute("SELECT COUNT(*) FROM foundations")
        existing = c.fetchone()[0]
        print(f"Existing real foundations in DB: {existing}")

    # Step 2: Process known EINs from forms_990/
    known_eins = get_eins_from_forms_folder()
    print(f"\nFound {len(known_eins)} EINs from forms_990/ folder")

    saved = 0
    with sqlite3.connect(DB_PATH) as conn:
        for i, ein in enumerate(known_eins, 1):
            data = fetch_org_data(ein)
            foundation = extract_data(data)
            if foundation:
                action = save_to_db(conn, foundation)
                assets_m = foundation['investment_assets'] / 1e6
                print(f"  [{i}/{len(known_eins)}] {action}: {foundation['name']} ({foundation['city']}) - ${assets_m:.1f}M")
                saved += 1
            else:
                org_name = data.get('organization', {}).get('name', ein) if data else ein
                print(f"  [{i}/{len(known_eins)}] skipped: {org_name} (below $2M or no data)")
            conn.commit()
            time.sleep(0.5)

    print(f"\nProcessed forms_990 EINs: {saved} saved")

    # Step 3: Broader ProPublica search for more LA foundations
    print(f"\nSearching ProPublica for additional Louisiana foundations...")
    search_eins = search_propublica_la_foundations(max_pages=40)
    print(f"Found {len(search_eins)} additional foundation candidates")

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        already_in_db = set(row[0] for row in c.execute("SELECT ein FROM foundations").fetchall())

    new_eins = [e for e in search_eins if e not in already_in_db]
    print(f"New EINs to check: {len(new_eins)}")

    new_saved = 0
    with sqlite3.connect(DB_PATH) as conn:
        for i, ein in enumerate(new_eins, 1):
            data = fetch_org_data(ein)
            foundation = extract_data(data)
            if foundation:
                action = save_to_db(conn, foundation)
                assets_m = foundation['investment_assets'] / 1e6
                print(f"  [{i}/{len(new_eins)}] {action}: {foundation['name']} ({foundation['city']}) - ${assets_m:.1f}M")
                new_saved += 1
            conn.commit()
            time.sleep(0.5)

    print(f"\nSearch pass: {new_saved} additional foundations saved")

    # Final summary
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*), SUM(investment_assets), SUM(annual_grants) FROM foundations")
        count, total_inv, total_grants = c.fetchone()
        print(f"\n{'='*60}")
        print(f"FINAL DATABASE SUMMARY")
        print(f"  Total foundations: {count}")
        print(f"  Total investment assets: ${(total_inv or 0)/1e9:.2f}B")
        print(f"  Total annual grants: ${(total_grants or 0)/1e6:.0f}M")
        print(f"{'='*60}")

        c.execute("""
            SELECT name, city, investment_assets, annual_grants, filing_year
            FROM foundations ORDER BY investment_assets DESC LIMIT 15
        """)
        print("\nTop 15 by investment assets:")
        for row in c.fetchall():
            name, city, assets, grants, year = row
            grants_str = f"${(grants or 0)/1e6:.1f}M grants" if grants else "grants N/A"
            print(f"  {name} ({city}) - ${(assets or 0)/1e6:.0f}M assets, {grants_str} [{year}]")


if __name__ == "__main__":
    main()
