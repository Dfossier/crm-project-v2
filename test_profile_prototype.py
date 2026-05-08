#!/usr/bin/env python3
"""Test profile prototype for one person"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import re

# Get a foundation with personnel and website
conn = sqlite3.connect('database/louisiana_foundations.db')

query = """
SELECT 
    f.id, f.name, f.website, f.city,
    p.name as personnel_name, p.title, p.linkedin_url
FROM foundations f
LEFT JOIN personnel_990 p ON f.id = p.foundation_id
WHERE f.website IS NOT NULL 
    AND f.website != ''
    AND p.name IS NOT NULL
ORDER BY f.id
LIMIT 5
"""

cursor = conn.execute(query)
rows = cursor.fetchall()

print("Available foundations with personnel and website:")
print("=" * 60)
for row in rows:
    fid, fname, fwebsite, fcity, pname, ptitle, plinkedin = row
    print(f"\nFoundation: {fname}")
    print(f"  Website: {fwebsite}")
    print(f"  City: {fcity}")
    print(f"  Personnel: {pname} ({ptitle})")
    if plinkedin:
        print(f"  LinkedIn: {plinkedin}")

conn.close()
