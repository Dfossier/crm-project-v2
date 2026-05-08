#!/usr/bin/env python3
"""
Update personnel_990 table with LinkedIn search results.
Reads search results from subagents and updates the database.
"""

import sqlite3
import json
import sys
from pathlib import Path
from typing import Optional, Dict, List, Any

DB_PATH = "/home/dfoss/crm/database/louisiana_foundations.db"
PERSONNEL_JSON = "/home/dfoss/louisiana_personnel.json"

class PersonnelLinkedInUpdater:
    """Updates personnel_990 table with LinkedIn search results."""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = OFF")
        self.cursor = self.conn.cursor()
        
    def ensure_columns_exist(self):
        """Ensure required columns exist in personnel_990 table."""
        columns = ["linkedin_url", "search_status", "notes"]
        for col in columns:
            if col not in self.get_table_columns():
                self.cursor.execute(f"ALTER TABLE personnel_990 ADD COLUMN {col} TEXT")
                print(f"Added column: {col}")
    
    def get_table_columns(self) -> List[str]:
        """Get list of columns in personnel_990 table."""
        self.cursor.execute("PRAGMA table_info(personnel_990)")
        return [row[1] for row in self.cursor.fetchall()]
    
    def update_row(self, row_id: int, linkedin_url: Optional[str], 
                   search_status: str, notes: Optional[str]):
        """Update a single row in personnel_990."""
        self.cursor.execute("""
            UPDATE personnel_990 
            SET linkedin_url = COALESCE(?, linkedin_url),
                search_status = ?,
                notes = COALESCE(?, notes)
            WHERE id = ?
        """, (linkedin_url, search_status, notes, row_id))
        if self.cursor.rowcount > 0:
            print(f"  Updated row {row_id}: {linkedin_url or search_status}")
        else:
            print(f"  Row {row_id} not found or unchanged")
    
    def bulk_update_from_json(self, personnel_data: List[Dict]):
        """Bulk update personnel data from JSON file."""
        # First, get existing IDs from database
        self.cursor.execute("SELECT id, name, title FROM personnel_990 WHERE linkedin_url IS NULL OR linkedin_url = 'No public LinkedIn profile found'")
        existing_rows = {row[0]: {"name": row[1], "title": row[2]} for row in self.cursor.fetchall()}
        
        print(f"\nFound {len(existing_rows)} rows to potentially update")
        
        for person in personnel_data:
            name = person.get("name", "").strip()
            title = person.get("title", "").strip()
            foundation_id = person.get("foundation_id")
            linkedin_url = person.get("linkedin_url", "").strip() or None
            
            if not name or not title:
                print(f"  Skipping: Missing name or title")
                continue

            self.cursor.execute("""
                SELECT id FROM personnel_990 
                WHERE name = ? AND title = ? AND foundation_id = ?
            """, (name, title, foundation_id))
            row = self.cursor.fetchone()
            
            if row:
                row_id = row[0]
                search_status = "completed" if linkedin_url else "no_public_profile"
                notes = f"Found profile for {name} ({title})" if linkedin_url else "No public LinkedIn profile found"
                self.update_row(row_id, linkedin_url, search_status, notes)
        
        self.conn.commit()
        print(f"\n✅ Bulk update complete")
    
    def close(self):
        """Close database connection."""
        self.conn.close()


def main():
    print("=" * 60)
    print("LinkedIn Search Results Updater")
    print("=" * 60)
    
    updater = PersonnelLinkedInUpdater()
    
    try:
        updater.ensure_columns_exist()
        
        if not Path(PERSONNEL_JSON).exists():
            print(f"\n❌ No personnel JSON file found at {PERSONNEL_JSON}")
            print("Populate this file with search results before running.")
            return 1

        print(f"\n📄 Reading personnel data from {PERSONNEL_JSON}...")
        with open(PERSONNEL_JSON, 'r') as f:
            personnel_data = json.load(f)
        
        print(f"   Found {len(personnel_data)} personnel records")
        updater.bulk_update_from_json(personnel_data)
        
        print("\n" + "=" * 60)
        print("📊 Update Summary")
        print("=" * 60)
        
        updater.cursor.execute("""
            SELECT 
                SUM(CASE WHEN linkedin_url LIKE 'https%' THEN 1 ELSE 0 END) as found_count,
                SUM(CASE WHEN linkedin_url = 'No public LinkedIn profile found' THEN 1 ELSE 0 END) as not_found_count
            FROM personnel_990
        """)
        summary = updater.cursor.fetchone()
        
        print(f"   LinkedIn profiles found: {summary[0]}")
        print(f"   No public profiles: {summary[1]}")
        
        print("\n✅ Database updated successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    finally:
        updater.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
