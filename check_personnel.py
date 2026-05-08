#!/usr/bin/env python3

import sqlite3

conn = sqlite3.connect('database/louisiana_foundations.db')
cursor = conn.cursor()

print("Current Personnel:")
cursor.execute('SELECT f.name as foundation, p.name, p.title, p.role FROM personnel p JOIN foundations f ON p.foundation_id = f.id LIMIT 20')
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} - {row[2]} ({row[3]})")

print("\nPersonnel by Role:")
cursor.execute('SELECT role, COUNT(*) FROM personnel GROUP BY role')
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()