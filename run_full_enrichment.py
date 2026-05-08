#!/usr/bin/env python3
"""Run bio enrichment on all personnel - optimized version"""

import sqlite3
from src.bio_enrichment import batch_enrich_all

conn = sqlite3.connect('database/louisiana_foundations.db')

# Clear existing profiles
cursor = conn.cursor()
cursor.execute('DELETE FROM personnel_profiles')
conn.commit()
print('Cleared existing profiles')
print()

# Run full enrichment with progress reporting
print("Starting bio enrichment (228 personnel, ~10-15 minutes)...")
enriched, total = batch_enrich_all(conn, limit=None)

print(f"\n\nResults: {enriched}/{total} profiles enriched")

# Show summary
cursor.execute("""
    SELECT 
        ROUND(AVG(confidence_score), 2) as avg_confidence,
        SUM(CASE WHEN bio_summary IS NOT NULL THEN 1 ELSE 0 END) as with_bio,
        SUM(CASE WHEN news_mentions IS NOT NULL THEN 1 ELSE 0 END) as with_news,
        COUNT(*) as total
    FROM personnel_profiles
""")
row = cursor.fetchone()

print(f"\nSummary:")
print(f"  Average confidence: {row[0]}")
print(f"  With bio: {row[1]}")
print(f"  With news: {row[2]}")
print(f"  Total profiles: {row[3]}")

# Show website status breakdown
cursor.execute("""
    SELECT website_status, COUNT(*) as count
    FROM personnel_profiles
    GROUP BY website_status
""")
print(f"\nWebsite status breakdown:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()
