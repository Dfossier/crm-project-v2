#!/usr/bin/env python3
"""Create personnel_profiles table and verify schema"""

import sqlite3

conn = sqlite3.connect('database/louisiana_foundations.db')
cursor = conn.cursor()

# Create personnel_profiles table
schema = """
CREATE TABLE IF NOT EXISTS personnel_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    personnel_id INTEGER REFERENCES personnel_990(id),
    bio_summary TEXT,
    career_history TEXT,
    education TEXT,
    news_mentions TEXT,
    location_verified INTEGER DEFAULT 0,
    data_sources TEXT,
    last_updated DATETIME,
    confidence_score REAL DEFAULT 0.0,
    website_status TEXT DEFAULT 'pending',
    linkedin_status TEXT DEFAULT 'pending',
    news_status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_personnel_profiles_personnel_id ON personnel_profiles(personnel_id);
CREATE INDEX IF NOT EXISTS idx_personnel_profiles_confidence ON personnel_profiles(confidence_score);
"""

cursor.executescript(schema)
conn.commit()

# Verify table created
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='personnel_profiles'")
if cursor.fetchone():
    print("✓ personnel_profiles table created")
else:
    print("✗ Table creation failed")

# Show table structure
cursor.execute("PRAGMA table_info(personnel_profiles)")
columns = cursor.fetchall()
print("\nTable structure:")
for col in columns:
    print(f"  {col[1]}: {col[2]}")

# Check existing tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print(f"\nTotal tables: {len(tables)}")
for t in sorted(tables):
    print(f"  - {t}")

conn.close()
