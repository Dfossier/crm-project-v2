#!/usr/bin/env python3

import sqlite3

conn = sqlite3.connect('database/louisiana_foundations.db')
cursor = conn.cursor()

print("Database Status:")
cursor.execute('SELECT COUNT(*) FROM foundations')
print(f"Foundations: {cursor.fetchone()[0]}")

cursor.execute('SELECT name, city, investment_assets FROM foundations ORDER BY investment_assets DESC LIMIT 3')
print("Top 3:")
for row in cursor.fetchall():
    print(f"  {row[0]} ({row[1]}): ${row[2]/1e6:.0f}M")

conn.close()