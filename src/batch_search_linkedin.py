#!/usr/bin/env python3
"""
Batch LinkedIn search for CRM personnel.
Processes in batches to avoid rate limits.
"""

import sqlite3
import json
import re
import time
import sys
import os

# Skip patterns (religious orders, etc.)
SKIP_PATTERNS = ['OP', 'O.P.', 'VERY REV', 'MOST REV', 'REV']

def clean_name(name):
    """Remove titles and suffixes from name"""
    clean = name.upper()
    for pattern in ['VERY REV', 'MOST REV', 'REV', 'OP', 'O.P.', 'MD', 'PHD', 'DR']:
        clean = clean.replace(pattern, '').strip()
    clean = re.sub(r',\s*(JR|SR|III|IV)$', '', clean, flags=re.IGNORECASE)
    return clean.strip()

def search_linkedin(name, employer=None):
    """Search LinkedIn for a person - returns URL or None"""
    clean = clean_name(name)
    if employer:
        query = f'{clean} {employer} LinkedIn'
    else:
        query = f'{clean} LinkedIn Louisiana'
    
    # This would be replaced with actual web_search call
    # For now, return placeholder
    return None

def main(batch_size=20, start_idx=0):
    # Load personnel without LinkedIn
    conn = sqlite3.connect('database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, title, employer 
        FROM personnel_990 
        WHERE linkedin_url IS NULL OR linkedin_url = ''
        ORDER BY id
    ''')
    
    all_records = cursor.fetchall()
    conn.close()
    
    # Load existing results if any
    results_file = 'linkedin_search_results.json'
    existing_results = {}
    if os.path.exists(results_file):
        with open(results_file) as f:
            results = json.load(f)
            existing_results = {r['id']: r for r in results}
    
    total = len(all_records)
    print(f"Total records: {total}")
    print(f"Starting from index: {start_idx}")
    print(f"Batch size: {batch_size}")
    
    # Process batch
    end_idx = min(start_idx + batch_size, total)
    found_count = 0
    skipped_count = 0
    
    for i in range(start_idx, end_idx):
        pid, name, title, employer = all_records[i]
        
        # Skip if already processed
        if pid in existing_results:
            continue
        
        # Check skip patterns
        should_skip = any(p in name.upper() for p in SKIP_PATTERNS)
        
        if should_skip:
            skipped_count += 1
            results.append({
                'id': pid,
                'name': name,
                'status': 'SKIPPED',
                'linkedin_url': None
            })
            continue
        
        # Would search here
        status = 'NOT FOUND'  # Placeholder
        
        results.append({
            'id': pid,
            'name': name,
            'status': status,
            'linkedin_url': None
        })
        
        print(f"[{i+1}/{total}] {name} -> {status}")
        
        # Rate limiting
        time.sleep(1)
    
    print(f"\nBatch complete: {found_count} found, {skipped_count} skipped")
    
    # Save results
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to {results_file}")

if __name__ == '__main__':
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    start_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    main(batch_size, start_idx)
