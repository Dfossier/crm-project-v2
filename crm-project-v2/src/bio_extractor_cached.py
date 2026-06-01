#!/usr/bin/env python3
"""
Bio extraction using cached search results (bypasses Cloudflare).
Uses web_search to get cached page content.
"""

import sqlite3
import json
import re
from datetime import datetime
from fuzzywuzzy import fuzz
from hermes_tools import web_search

# Board pages - use search queries to get cached versions
BOARD_QUERIES = {
    "LSUHS": ("site:lsuhsfoundation.org board", 26),
    "BRAF": ("site:braf.org board of directors", 9),
    "CFNLA": ("site:cfnla.org board", 19),
    "BRF": ("site:brfla.org board leadership", 20),
    "IDF": ("site:internationaldominicanfoundation.org board", 21),
    "LSU Foundation": ("site:lsufoundation.org board directors", 4),
    "SWLAC": ("site:swlacharterfoundation.org board trustees", 25),
}


def extract_bios_from_search_results(search_results, foundation_name):
    """
    Extract bios from web_search results (title + description).
    """
    bios = {}
    
    if not search_results or 'data' not in search_results or 'web' not in search_results['data']:
        return bios
    
    for result in search_results['data']['web']:
        title = result.get('title', '')
        description = result.get('description', '')
        
        # Combine title and description
        content = f"{title} {description}"
        
        # Strategy 1: "Name. Bio text" pattern
        # Example: "Thomas J. Mr. Adamek is a founder and president..."
        pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z.]+)+)\s+(Mr\.|Ms\.|Mrs\.)?\s+([A-Z][a-z]+)\s+is?\s+(.+?)(?:\s+[A-Z][a-z]+|$)'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            name = match.group(1).strip()
            role = match.group(4).strip()
            
            # Clean up role text
            role = re.sub(r'\s+', ' ', role).strip()
            role = role.rstrip('.,')
            
            if 4 < len(name) < 60 and 10 < len(role) < 200:
                if name not in bios:
                    bios[name] = role
        
        # Strategy 2: "Name, Role" pattern
        pattern2 = r'([A-Z][a-z]+\s+[A-Z]\.[A-Z]\.\s+[a-z]+),?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)'
        for match in re.finditer(pattern2, content):
            name = match.group(1).strip()
            role = match.group(2).strip()
            
            if 4 < len(name) < 60 and 5 < len(role) < 100:
                if name not in bios:
                    bios[name] = role
        
        # Strategy 3: Name followed by "is" or "serves as"
        pattern3 = r'([A-Z][A-Za-z\.]+\s+[A-Z][A-Za-z\.]+)\s+(?:is|serves as)\s+([A-Za-z, ]+?(?:\s+CEO|\s+President|\s+Founder|\s+Chair|\s+Director|\s+Partner|\s+Founder|\s+Vice President))'
        for match in re.finditer(pattern3, content, re.IGNORECASE):
            name = match.group(1).strip()
            role = match.group(2).strip()
            
            if 4 < len(name) < 60 and 10 < len(role) < 150:
                if name not in bios:
                    bios[name] = role
    
    return bios


def scrape_bios_from_cache(foundation_name, query, foundation_id):
    """Scrape bios from cached search results."""
    print(f"\n[{foundation_name}]")
    print(f"  Query: {query}")
    
    try:
        search_results = web_search(query)
        
        if not search_results or 'data' not in search_results:
            return {'foundation': foundation_name, 'error': 'No search results'}
        
        bios = extract_bios_from_search_results(search_results, foundation_name)
        
        # Show sample results
        if bios:
            print(f"  Found {len(bios)} bios from cache")
            for name, bio in list(bios.items())[:3]:
                print(f"    - {name}: {bio[:60]}...")
        
        return {
            'foundation': foundation_name,
            'foundation_id': foundation_id,
            'bios': bios,
            'bio_count': len(bios)
        }
        
    except Exception as e:
        return {'foundation': foundation_name, 'error': str(e)}


def normalize_name(name):
    """Normalize name for fuzzy matching."""
    name = name.upper()
    name = name.replace('MD', '').replace('DR', '').replace('PHD', '')
    name = name.replace(' PHD', '').replace(' MD', '').replace(' DR', '')
    name = re.sub(r',\s*Jr\.', '', name, flags=re.I)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def match_and_update_bios(all_bios, board_queries):
    """Match extracted bios to database and update."""
    conn = sqlite3.connect('/home/dfoss/crm/database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, foundation_id 
        FROM personnel_990 
        WHERE is_board_member = 1
    """)
    board_members = cursor.fetchall()
    
    print("\n" + "=" * 70)
    print("MATCHING BIOS TO DATABASE")
    print("=" * 70)
    
    updated_count = 0
    matched = []
    
    for pid, pname, pfid in board_members:
        db_name_norm = normalize_name(pname)
        
        for fname, fbios in all_bios.items():
            for bname, (bquery, bfoundation_id) in board_queries.items():
                if bname == fname and pfid == bfoundation_id:
                    for bio_name, bio in fbios.items():
                        bio_name_norm = normalize_name(bio_name)
                        similarity = fuzz.ratio(db_name_norm, bio_name_norm)
                        
                        if similarity >= 75 and bio and len(bio.strip()) > 10:
                            cursor.execute("""
                                UPDATE personnel_990 
                                SET bio = ? 
                                WHERE id = ?
                            """, (bio, pid))
                            updated_count += 1
                            matched.append({
                                'personnel_id': pid,
                                'name': pname,
                                'bio': bio,
                                'similarity': similarity
                            })
                            break
    
    conn.commit()
    
    matched.sort(key=lambda x: x['similarity'], reverse=True)
    
    for m in matched[:25]:
        print(f"  ✓ {m['name'][:35]:<35} (match: {m['similarity']:3.0f}%)")
        print(f"      Bio: {m['bio'][:70]}...")
    
    if len(matched) > 25:
        print(f"\n  ... and {len(matched) - 25} more matches")
    
    conn.close()
    return updated_count, matched


def main():
    """Main extraction pipeline."""
    print("=" * 70)
    print("BIO EXTRACTION PIPELINE (Cached Search Results)")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_bios = {}
    results = []
    
    for foundation_name, (query, foundation_id) in BOARD_QUERIES.items():
        result = scrape_bios_from_cache(foundation_name, query, foundation_id)
        results.append(result)
        
        if 'error' not in result:
            all_bios[foundation_name] = result['bios']
        else:
            print(f"  Error: {result.get('error')}")
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with open(f'/home/dfoss/crm/extracted_bios_cached_{timestamp}.json', 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'results': results,
            'bios': all_bios
        }, f, indent=2)
    
    # Match and update
    updated_count, matched = match_and_update_bios(all_bios, BOARD_QUERIES)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for result in results:
        foundation = result['foundation']
        if 'error' not in result:
            print(f"  {foundation}: {result['bio_count']} bios")
        else:
            print(f"  {foundation}: ERROR - {result.get('error', 'Unknown')}")
    
    print(f"\n  Total bios extracted: {sum(r.get('bio_count', 0) for r in results)}")
    print(f"  Database updates: {updated_count}")
    
    # Final stats
    conn = sqlite3.connect('/home/dfoss/crm/database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1")
    total_board = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1 AND bio IS NOT NULL AND bio != ''")
    with_bios = cursor.fetchone()[0]
    
    print(f"\n  Board members with bios: {with_bios}/{total_board} ({100*with_bios/total_board:.1f}%)")
    
    conn.close()
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Results saved to: /home/dfoss/crm/extracted_bios_cached_{timestamp}.json")


if __name__ == '__main__':
    main()
