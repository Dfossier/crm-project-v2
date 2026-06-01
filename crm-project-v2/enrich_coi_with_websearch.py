#!/usr/bin/env python3
"""
Enrich centers_of_influence records with contact info using web search.
Uses subprocess to call web search via curl.
"""

import sqlite3
import subprocess
import json
import time
import shlex

def web_search(query, limit=3):
    """Execute web search using curl."""
    try:
        # Build curl command for web search
        cmd = f'web_search --query "{query}" --limit {limit}'
        result = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except:
                pass
        return {'data': {'web': []}}
    except Exception as e:
        print(f"  Search error: {e}")
        return {'data': {'web': []}}

def search_company_contact(employer, city="Louisiana"):
    """Search for company contact information."""
    if not employer or employer.strip() == '':
        return {}
    
    # Escape special characters
    safe_employer = employer.replace('"', '').replace('$', '')
    query = f'"{safe_employer}" contact phone email {city}'
    
    results = web_search(query, limit=3)
    
    info = {}
    if results and 'data' in results and 'web' in results['data']:
        for result in results['data']['web'][:3]:
            # Look for contact info in title/description
            text = (result.get('title', '') + ' ' + result.get('description', '')).lower()
            
            # Extract URLs that might have contact pages
            if 'contact' in text or 'phone' in text or 'email' in text or 'directory' in text:
                info['contact_page'] = result.get('url')
                info['title'] = result.get('title')
                break
        
        # If no contact page found, return homepage
        if not info and results['data']['web']:
            info['homepage'] = results['data']['web'][0].get('url')
    
    return info

def main():
    conn = sqlite3.connect('database/louisiana_foundations.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get COIs with employer info but missing contact details
    cur.execute('''
        SELECT id, name, employer, linkedin_url
        FROM centers_of_influence
        WHERE employer IS NOT NULL 
          AND employer != ''
          AND employer_address IS NULL
        LIMIT 30
    ''')
    
    cois = cur.fetchall()
    print(f"Enriching contact info for {len(cois)} centers of influence...\n")
    
    updated = 0
    for coi in cois:
        print(f"Searching: {coi['name']} @ {coi['employer']}")
        
        # Search for company contact info
        company_info = search_company_contact(coi['employer'])
        
        if company_info:
            notes = []
            if company_info.get('contact_page'):
                notes.append(f"Contact: {company_info['contact_page']} ({company_info.get('title', '')})")
            if company_info.get('homepage'):
                notes.append(f"Homepage: {company_info['homepage']}")
            
            if notes:
                cur.execute('''
                    UPDATE centers_of_influence 
                    SET notes = COALESCE(notes, '') || '\n' || ?
                    WHERE id = ?
                ''', ('\n'.join(notes), coi['id']))
                conn.commit()
                print(f"  Found: {' | '.join(notes)}")
                updated += 1
            else:
                print(f"  No useful info found")
        else:
            print(f"  No results")
        
        time.sleep(1)  # Rate limiting
    
    print(f"\n=== Summary ===")
    print(f"Processed: {len(cois)}")
    print(f"Contact info found: {updated}")
    
    # Show current stats
    cur.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(phone) as has_phone,
            COUNT(email) as has_email,
            COUNT(employer) as has_employer,
            COUNT(notes) as has_notes
        FROM centers_of_influence
    ''')
    stats = cur.fetchone()
    print(f"\n=== Current COI Stats ===")
    print(f"Total COIs: {stats['total']}")
    print(f"With phone: {stats['has_phone']}")
    print(f"With email: {stats['has_email']}")
    print(f"With employer: {stats['has_employer']}")
    print(f"With notes: {stats['has_notes']}")
    
    conn.close()

if __name__ == '__main__':
    main()
