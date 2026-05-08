#!/usr/bin/env python3
import time
"""Test optimized bio enrichment on 5 records"""

import sqlite3
from src.bio_enrichment import batch_enrich_all

conn = sqlite3.connect('database/louisiana_foundations.db')
cursor = conn.cursor()

# Clear existing profiles
cursor.execute('DELETE FROM personnel_profiles')
conn.commit()
print('Cleared existing profiles')
print()

# Test on 5 records
print("Testing optimized enrichment on 5 records...")
start_time = time.time()
enriched, total = batch_enrich_all(conn, limit=5)
elapsed = time.time() - start_time

print(f"\nDone: {enriched}/{total} in {elapsed:.1f} seconds")
print(f"Average: {elapsed/enriched:.1f} seconds per record")

# Show results
cursor.execute('SELECT personnel_id, bio_summary, confidence_score, website_status FROM personnel_profiles')
for row in cursor.fetchall():
    print(f"\nPersonnel {row[0]}:")
    print(f"  Confidence: {row[2]:.1f}")
    print(f"  Website: {row[3]}")
    if row[1]:
        print(f"  Bio: {row[1][:100]}...")
    else:
        print(f"  Bio: None")

conn.close()
