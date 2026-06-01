#!/usr/bin/env python3
"""
Extract biographies from LinkedIn profiles in the CRM database.
Stores extracted data in a new 'biography' column.
"""

import sqlite3
import json
import os

# Path to database
DB_PATH = 'database/louisiana_foundations.db'

def ensure_biography_column(conn):
    """Add biography column if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(personnel_990)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'biography' not in columns:
        cursor.execute("ALTER TABLE personnel_990 ADD COLUMN biography TEXT")
        conn.commit()
        print("Added biography column")

def extract_bios_from_database():
    """
    Extract all personnel records with LinkedIn URLs.
    Returns list of (id, name, linkedin_url).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, linkedin_url 
        FROM personnel_990 
        WHERE linkedin_url LIKE "https%"
        LIMIT 20
    ''')
    
    records = cursor.fetchall()
    conn.close()
    return records

def save_bios_to_json(bios_data, output_path='exports/linkedin_bios.json'):
    """Save extracted biography data to JSON file."""
    os.makedirs('exports', exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(bios_data, f, indent=2)
    print(f"Saved {len(bios_data)} bios to {output_path}")

def main():
    """Main function to extract bios."""
    print("=== LinkedIn Biography Extractor ===")
    print("This script will:")
    print("1. Extract personnel data from database")
    print("2. Visit each LinkedIn profile")
    print("3. Extract biography information")
    print("4. Save to JSON and update database")
    print()
    
    records = extract_bios_from_database()
    print(f"Found {len(records)} records with LinkedIn URLs")
    print()
    
    # Show sample records
    print("Sample records:")
    for i, (id, name, url) in enumerate(records[:5]):
        print(f"  {i+1}. {name} - {url}")
    
    print()
    print(f"Total: {len(records)} profiles to process")
    print()
    
    # For now, just export the list - actual extraction requires browser automation
    bios_data = []
    for id, name, url in records:
        bios_data.append({
            "id": id,
            "name": name,
            "linkedin_url": url,
            "biography": "Pending extraction",
            "title": None,
            "company": None,
            "location": None,
            "education": [],
            "experience": []
        })
    
    save_bios_to_json(bios_data)
    print()
    print("Biography extraction requires browser automation.")
    print("Use the browser tool to visit profiles and extract bio data.")

if __name__ == '__main__':
    main()
