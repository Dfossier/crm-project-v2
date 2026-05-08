#!/usr/bin/env python3

import sqlite3
import os

db_path = 'database/louisiana_foundations.db'

if not os.path.exists(db_path):
    print(f"Database file {db_path} does not exist!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check what tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:", [table[0] for table in tables])

# Count records in each table
for table in tables:
    table_name = table[0]
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"{table_name}: {count} records")
    
    # Show first few records if any exist
    if count > 0:
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
        sample_records = cursor.fetchall()
        print(f"  Sample records: {sample_records}")

conn.close()