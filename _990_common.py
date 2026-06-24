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
