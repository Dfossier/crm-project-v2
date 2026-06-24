#!/usr/bin/env python3
"""
Ingest real IRS 990 XML data for Louisiana foundations.
Uses HTTP range requests (remotezip) to fetch only matching XML files
from the IRS TEOS bulk ZIP archives — no full ZIP download needed.

Handles both 990 and 990PF form types.
For 2024: uses XML_BATCH_ID column from index to find the right ZIP.
For 2023: scans ZIP central directories to locate each file by OBJECT_ID.
"""

import sqlite3
import logging
import time
from pathlib import Path
from collections import defaultdict

import defusedxml.ElementTree as ET

from _990_common import (
    IRS_NS, BASE_URL, INDEX_URL, ZIP_URL, TARGET_TYPES,
    fetch_index, get_batch_names, build_batch_map,
    deduplicate_index_rows, _t, _yn,
)

DB_PATH = Path(__file__).parent / "database/louisiana_foundations.db"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Database ────────────────────────────────────────────────────────────────

def get_foundation_eins(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, ein, name FROM foundations ORDER BY id")
    return {r[1]: (r[0], r[2]) for r in cur.fetchall()}

def ensure_linkedin_col(conn):
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(personnel_990)").fetchall()]
    if 'linkedin_url' not in cols:
        cur.execute("ALTER TABLE personnel_990 ADD COLUMN linkedin_url TEXT")
        conn.commit()

def clear_synthetic_personnel(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM personnel_990 WHERE filing_year = 2022")
    n = cur.rowcount
    conn.commit()
    log.info(f"Cleared {n} synthetic personnel records (filing_year=2022)")

def insert_personnel(conn, foundation_id, people, filing_year):
    cur = conn.cursor()
    inserted = 0
    for p in people:
        cur.execute("""
            INSERT OR IGNORE INTO personnel_990
                (foundation_id, name, title, role_type,
                 is_officer, is_director, is_trustee, is_key_employee,
                 hours_per_week, compensation, benefits, expense_account,
                 filing_year, is_president, is_vice_president, is_secretary,
                 is_treasurer, is_cfo, is_ceo, is_chair, is_990_filer)
            VALUES (?,?,?,?,?,?,?,?,?,?,0,0,?,?,?,?,?,?,?,?,?)
        """, (
            foundation_id,
            p['name'], p['title'], p['role_type'],
            int(p['is_officer']), int(p['is_director']),
            int(p['is_director']), int(p['is_key_employee']),
            p.get('hours'), p.get('compensation', 0),
            filing_year,
            int(p['is_president']), int(p['is_vp']), int(p['is_secretary']),
            int(p['is_treasurer']), int(p['is_cfo']), int(p['is_ceo']),
            int(p['is_chair']), 0,
        ))
        inserted += cur.rowcount
    conn.commit()
    return inserted

# ── XML parsing ─────────────────────────────────────────────────────────────

def title_flags(title):
    t = title.upper()
    return {
        'is_president': 'PRESIDENT' in t and 'VICE' not in t,
        'is_vp':        'VICE' in t and 'PRESIDENT' in t,
        'is_secretary': 'SECRETARY' in t,
        'is_treasurer': 'TREASURER' in t,
        'is_cfo':       ('CHIEF FINANCIAL' in t) or ('CFO' in t),
        'is_ceo':       ('CHIEF EXECUTIVE' in t) or (' CEO' in t) or t.startswith('CEO'),
        'is_chair':     'CHAIR' in t,
    }

def parse_990_xml(xml_bytes, form_type):
    """Parse officer/director list from a 990 or 990PF XML filing."""
    people = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log.warning(f"XML parse error: {e}")
        return people

    ns = IRS_NS

    if form_type == '990PF':
        # 990PF: OfficerDirTrstKeyEmplInfoGrp > OfficerDirTrstKeyEmplGrp
        for info_grp in root.iter(f'{{{ns}}}OfficerDirTrstKeyEmplInfoGrp'):
            for grp in info_grp.iter(f'{{{ns}}}OfficerDirTrstKeyEmplGrp'):
                name  = _t(grp, 'PersonNm')
                title = _t(grp, 'TitleTxt')
                if not name:
                    continue
                comp_txt = _t(grp, 'CompensationAmt')
                try:
                    comp = float(comp_txt)
                except ValueError:
                    comp = 0.0
                hours_txt = _t(grp, 'AverageHrsPerWkDevotedToPosRt')
                try:
                    hours = float(hours_txt)
                except ValueError:
                    hours = None
                flags = title_flags(title)
                people.append({
                    'name': name, 'title': title,
                    'role_type': 'officer',
                    'is_officer': True, 'is_director': False,
                    'is_key_employee': False,
                    'hours': hours, 'compensation': comp,
                    **flags,
                })
    else:
        # 990: Form990PartVIISectionAGrp
        for grp in root.iter(f'{{{ns}}}Form990PartVIISectionAGrp'):
            name  = _t(grp, 'PersonNm')
            title = _t(grp, 'TitleTxt')
            if not name:
                continue

            is_officer  = _yn(_t(grp, 'OfficerInd'))
            is_director = _yn(_t(grp, 'IndividualTrusteeOrDirectorInd'))
            is_key_emp  = _yn(_t(grp, 'KeyEmployeeInd'))
            is_hce      = _yn(_t(grp, 'HighestCompensatedEmployeeInd'))

            if is_officer:
                role_type = 'officer'
            elif is_director:
                role_type = 'trustee'
            elif is_key_emp or is_hce:
                role_type = 'key_employee'
            else:
                role_type = 'officer'

            comp_txt = _t(grp, 'ReportableCompFromOrgAmt')
            try:
                comp = float(comp_txt)
            except ValueError:
                comp = 0.0

            hours_txt = _t(grp, 'AverageHoursPerWeekRt')
            try:
                hours = float(hours_txt)
            except ValueError:
                hours = None

            flags = title_flags(title)
            people.append({
                'name': name, 'title': title,
                'role_type': role_type,
                'is_officer': is_officer,
                'is_director': is_director,
                'is_key_employee': is_key_emp or is_hce,
                'hours': hours, 'compensation': comp,
                **flags,
            })

    return people

# ── Core ingestion ──────────────────────────────────────────────────────────

def process_batch(conn, ein_map, batch, year, filings, already_done):
    """Download XML files from one batch ZIP and insert personnel."""
    from remotezip import RemoteZip
    zip_url = ZIP_URL.format(year=year, batch=batch)
    log.info(f"Opening {batch} ({len(filings)} filing(s))")
    try:
        with RemoteZip(zip_url) as rz:
            for f in filings:
                ein      = f['EIN']
                obj_id   = f['OBJECT_ID']
                period   = f['TAX_PERIOD']
                ftype    = f['RETURN_TYPE']
                name_irs = f['TAXPAYER_NAME']
                filing_year = int(period[:4]) if period and len(period) >= 4 else year

                zip_path = f"{batch}/{obj_id}_public.xml"
                try:
                    xml_bytes = rz.read(zip_path)
                except KeyError:
                    log.warning(f"  {zip_path} not found in ZIP")
                    continue

                people = parse_990_xml(xml_bytes, ftype)
                if not people:
                    log.warning(f"  No officers parsed — EIN {ein} ({name_irs}) {ftype}")
                    continue

                fid, _ = ein_map[ein]
                n = insert_personnel(conn, fid, people, filing_year)
                log.info(f"  EIN {ein} {name_irs}: {len(people)} people, {n} new rows")
                already_done.add(ein)
                time.sleep(0.05)
    except Exception as e:
        log.warning(f"  Failed on {batch}: {e}")

def process_year_batch_id(conn, ein_map, year, target_eins, already_done):
    """
    Process one year whose index CSV has an XML_BATCH_ID column (2024, 2025+).
    Returns the set of EINs successfully processed.
    """
    log.info(f"=== Year {year} ===")
    rows = fetch_index(year, target_eins)

    # Deduplicate: prefer 990 over 990PF; keep only most recent period per EIN
    best = deduplicate_index_rows(rows)

    by_batch = defaultdict(list)
    for r in best.values():
        batch = r.get('XML_BATCH_ID', '').strip().upper()
        if batch:
            by_batch[batch].append(r)

    for batch, filings in sorted(by_batch.items()):
        process_batch(conn, ein_map, batch, year, filings, already_done)


def ingest():
    conn = sqlite3.connect(DB_PATH)
    ein_map     = get_foundation_eins(conn)
    target_eins = set(ein_map.keys())
    ensure_linkedin_col(conn)
    clear_synthetic_personnel(conn)

    already_done = set()

    # ── 2025 ────────────────────────────────────────────────────────────────
    process_year_batch_id(conn, ein_map, 2025, target_eins, already_done)

    # ── 2024 (foundations not found in 2025) ────────────────────────────────
    remaining = target_eins - already_done
    if remaining:
        process_year_batch_id(conn, ein_map, 2024, remaining, already_done)

    # ── 2023 (foundations not found in 2025 or 2024) ────────────────────────
    remaining = target_eins - already_done
    if remaining:
        log.info(f"=== Year 2023 ({len(remaining)} foundations still needed) ===")
        rows_2023 = fetch_index(2023, remaining)

        # Deduplicate per EIN
        best23 = deduplicate_index_rows(rows_2023)

        if best23:
            log.info("  Building 2023 batch map (scanning ZIP central directories)...")
            obj_to_batch = build_batch_map(2023, [r['OBJECT_ID'] for r in best23.values()])

            by_batch23 = defaultdict(list)
            for r in best23.values():
                batch = obj_to_batch.get(r['OBJECT_ID'])
                if batch:
                    by_batch23[batch].append(r)
                else:
                    log.warning(f"  No batch found for EIN {r['EIN']} OBJ {r['OBJECT_ID']}")

            for batch, filings in sorted(by_batch23.items()):
                process_batch(conn, ein_map, batch, 2023, filings, already_done)

    # ── Summary ─────────────────────────────────────────────────────────────
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM personnel_990")
    total_people = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT foundation_id) FROM personnel_990")
    foundations_covered = cur.fetchone()[0]
    conn.close()

    print(f"\n=== Ingestion Complete ===")
    print(f"Foundations with real data: {foundations_covered} / {len(ein_map)}")
    print(f"Total personnel records:    {total_people}")

    not_found = target_eins - already_done
    if not_found:
        print(f"\nFoundations with no electronic 990 filing ({len(not_found)}):")
        for ein in sorted(not_found):
            _, fname = ein_map.get(ein, (None, ein))
            print(f"  {ein}  {fname}")

if __name__ == "__main__":
    ingest()
