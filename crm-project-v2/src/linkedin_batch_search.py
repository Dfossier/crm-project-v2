#!/usr/bin/env python3
"""
LinkedIn batch search script.
Run with: python3 src/linkedin_batch_search.py [batch_number]
"""

import sqlite3
import json
import re
import os

# Skip patterns
SKIP_PATTERNS = ['OP', 'O.P.', 'VERY REV', 'MOST REV', 'REV']

def clean_name(name):
    clean = name.upper()
    for pattern in ['VERY REV', 'MOST REV', 'REV', 'OP', 'O.P.', 'MD', 'PHD', 'DR']:
        clean = clean.replace(pattern, '').strip()
    clean = re.sub(r',\s*(JR|SR|III|IV)$', '', clean, flags=re.IGNORECASE)
    return clean.strip()

def build_query(name, employer=None):
    clean = clean_name(name)
    if employer:
        return f'{clean} {employer} LinkedIn'
    return f'{clean} LinkedIn Louisiana'

def main():
    conn = sqlite3.connect('database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    # Get all records without LinkedIn
    cursor.execute('''
        SELECT id, name, title, employer 
        FROM personnel_990 
        WHERE linkedin_url IS NULL OR linkedin_url = ''
        ORDER BY id
    ''')
    
    all_records = cursor.fetchall()
    conn.close()
    
    print(f"Total records to search: {len(all_records)}")
    
    # Load existing results
    existing = {}
    if os.path.exists('linkedin_search_results.json'):
        with open('linkedin_search_results.json') as f:
            for r in json.load(f):
                existing[r['id']] = r
    
    # Build list of records to search (skip already processed)
    to_search = []
    for pid, name, title, employer in all_records:
        if pid not in existing:
            to_search.append((pid, name, title, employer))
    
    print(f"Records remaining: {len(to_search)}")
    
    # Generate queries for batch processing
    print("\n" + "="*60)
    print("Search queries to run:")
    print("="*60)
    
    for pid, name, title, employer in to_search:
        # Check skip patterns
        if any(p in name.upper() for p in SKIP_PATTERNS):
            print(f"[SKIP] {pid}: {name}")
            continue
        
        query = build_query(name, employer)
        print(f"{pid}: {clean_name(name)}")
        print(f"    Query: {query}")
        print()

if __name__ == '__main__':
    main()
