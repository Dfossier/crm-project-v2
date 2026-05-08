#!/usr/bin/env python3
"""Test bio enrichment on 20 records"""

import sqlite3
from src.bio_enrichment import batch_enrich_all

conn = sqlite3.connect('database/louisiana_foundations.db')
cursor = conn.cursor()
cursor.execute('DELETE FROM personnel_profiles')
conn.commit()
print('Starting enrichment on 20 records...')
enriched, total = batch_enrich_all(conn, limit=20)
print(f'Done: {enriched}/{total}')
cursor.execute('SELECT COUNT(*) FROM personnel_profiles')
print(f'In database: {cursor.fetchone()[0]}')
conn.close()
