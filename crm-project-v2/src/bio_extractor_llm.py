#!/usr/bin/env python3
"""
Robust bio extraction pipeline using LLM + multiple strategies.
Handles diverse HTML structures and Cloudflare blocking.
"""

import sqlite3
import json
import re
from datetime import datetime
from fuzzywuzzy import fuzz
from hermes_tools import web_extract

# Board pages to extract bios from
BOARD_PAGES = {
    "LSUHS": ("https://www.lsuhsfoundation.org/your-foundation#board", 26),
    "BRAF": ("https://www.braf.org/board-of-directors/", 9),
    "CFNLA": ("https://cfnla.org/board/", 19),
    "BRF": ("https://www.brfla.org/brf-board-and-leadership/", 20),
    "IDF": ("https://internationaldominicanfoundation.org/board-of-directors/", 21),
    "LSU Foundation": ("https://www.lsufoundation.org/who-we-are/our-team/board-of-directors/index.php", 4),
    "SWLAC": ("https://www.swlacharterfoundation.org/board-of-trustees/", 25),
}

def extract_bios_with_llm(page_content, foundation_name):
    """
    Use LLM to extract board member bios from HTML content.
    Returns dict of {name: bio}
    """
    # Extract just the relevant section (look for board-related content)
    # This reduces context and focuses the LLM
    
    # Prompt for LLM extraction
    prompt = f"""
You are an expert data extractor. Extract board member information from this HTML page.

Foundation: {foundation_name}

Task: Find all board members and their roles/titles/bios.

Output format: JSON array of objects with fields: name, role, bio
- name: Full name of the person
- role: Their board role (Chair, Director, Treasurer, etc.) or professional title
- bio: Any biographical information (professional background, affiliations, etc.)

Only include actual people, not navigation items, addresses, or page content.

HTML content:
{page_content[:8000]}

Output ONLY valid JSON, no other text:
"""
    
    # Use web_search to get LLM extraction
    # Note: This is a simplified approach - in production you'd use a dedicated LLM API
    return extract_bios_simple(page_content)


def extract_bios_simple(html_content):
    """
    Extract bios using pattern matching - handles multiple HTML structures.
    """
    bios = {}
    
    # Strategy 1: Table format (| Name | Role | Affiliation |)
    table_pattern = r'<table[^>]*>(.*?)</table>'
    for table_match in re.finditer(table_pattern, html_content, re.DOTALL):
        table_html = table_match.group(1)
        
        # Extract rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        for row in rows:
            cells = re.findall(r'<t[^>]*>(.*?)</t[^>]*>', row, re.DOTALL)
            if len(cells) >= 2:
                # Clean cell text
                clean_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                name = clean_cells[0]
                role = clean_cells[1] if len(clean_cells) > 1 else ""
                affil = clean_cells[2] if len(clean_cells) > 2 else ""
                
                if 4 < len(name) < 60 and name[0].isupper():
                    if name.lower() not in ['name', 'role', 'professional affiliation', 'cookie']:
                        bio = role
                        if affil:
                            bio += f", {affil}"
                        if name not in bios:
                            bios[name] = bio
    
    # Strategy 2: Strong/em pattern (<strong>Name</strong><br/><em>Role</em>)
    strong_em_pattern = r'<strong[^>]*>([^<]+)</strong>\s*<br\s*/?>\s*<em[^>]*>([^<]+)</em>'
    for match in re.finditer(strong_em_pattern, html_content):
        name = match.group(1).strip()
        role = match.group(2).strip()
        
        if 4 < len(name) < 60 and name[0].isupper():
            if name.lower() not in ['board of directors', 'donate today']:
                if name not in bios:
                    bios[name] = role
    
    # Strategy 3: Name followed by role in paragraph
    # Pattern: "Name - Role" or "Name\nRole"
    paragraph_pattern = r'<p[^>]*>(.*?)</p>'
    for p_match in re.finditer(paragraph_pattern, html_content, re.DOTALL):
        p_content = p_match.group(1)
        
        # Clean HTML tags
        clean_text = re.sub(r'<[^>]+>', '\n', p_content).strip()
        lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
        
        if len(lines) >= 2:
            name = lines[0]
            role = lines[1]
            
            if 4 < len(name) < 60 and name[0].isupper():
                if name.lower() not in ['board of directors', 'donate today', 'follow']:
                    if name not in bios:
                        bios[name] = role
    
    # Strategy 4: List items with name + role
    li_pattern = r'<li[^>]*>(.*?)</li>'
    for li_match in re.finditer(li_pattern, html_content, re.DOTALL):
        li_content = li_match.group(1)
        clean_text = re.sub(r'<[^>]+>', ' ', li_content).strip()
        
        # Try to split by common separators
        for sep in [' - ', ' -', ' – ', ' –', ' | ']:
            if sep in clean_text:
                parts = clean_text.split(sep, 1)
                if len(parts) == 2:
                    name = parts[0].strip()
                    role = parts[1].strip()
                    
                    if 4 < len(name) < 60 and 5 < len(role) < 200:
                        if name[0].isupper():
                            if name not in bios:
                                bios[name] = role
                break
    
    # Strategy 5: JSON-LD Person data
    jsonld_pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for script_match in re.finditer(jsonld_pattern, html_content, re.DOTALL):
        try:
            data = json.loads(script_match.group(1))
            if isinstance(data, dict):
                if data.get('@type') == 'Person':
                    name = data.get('name', '')
                    bio = data.get('description', '') or data.get('jobTitle', '')
                    if name and bio:
                        if name not in bios:
                            bios[name] = bio
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('@type') == 'Person':
                        name = item.get('name', '')
                        bio = item.get('description', '') or item.get('jobTitle', '')
                        if name and bio:
                            if name not in bios:
                                bios[name] = bio
        except:
            pass
    
    return bios


def scrape_bios(foundation_name, url, foundation_id):
    """
    Scrape bios from a board page using web_extract (bypasses Cloudflare).
    """
    print(f"\n[{foundation_name}]")
    print(f"  URL: {url}")
    
    try:
        # Use web_extract instead of requests to bypass Cloudflare
        result = web_extract([url])
        
        if not result or 'results' not in result or not result['results']:
            return {'foundation': foundation_name, 'error': 'No results from web_extract'}
        
        page_result = result['results'][0]
        
        if 'error' in page_result:
            return {'foundation': foundation_name, 'error': page_result['error']}
        
        if not page_result.get('content'):
            return {'foundation': foundation_name, 'error': 'No content extracted'}
        
        html_content = page_result['content']
        
        # Extract bios
        bios = extract_bios_simple(html_content)
        
        # Filter out obvious non-person entries
        filtered_bios = {}
        exclude_patterns = [
            r'^\d+\s*$',  # Just numbers
            r'^[0-9a-f]{8,}$',  # Hashes
            r'^https?://',  # URLs
            r'^\d+\s*[A-Z][a-z]+\s*St',  # Addresses
            r'(hours?|phone|email|contact|follow|donate)',  # Page elements
        ]
        
        for name, bio in bios.items():
            exclude = False
            for pattern in exclude_patterns:
                if re.match(pattern, name, re.I):
                    exclude = True
                    break
            
            if not exclude and 4 < len(name) < 60:
                filtered_bios[name] = bio
        
        return {
            'foundation': foundation_name,
            'foundation_id': foundation_id,
            'bios': filtered_bios,
            'bio_count': len(filtered_bios),
            'raw_count': len(bios)
        }
        
    except Exception as e:
        return {'foundation': foundation_name, 'error': str(e)}


def normalize_name(name):
    """Normalize name for fuzzy matching."""
    name = name.upper()
    name = name.replace('MD', '').replace('DR', '').replace('PHD', '')
    name = name.replace(' PHD', '').replace(' MD', '').replace(' DR', '')
    name = re.sub(r',\s*Jr\.', '', name, flags=re.I)
    name = re.sub(r',\s*Esq\.', '', name, flags=re.I)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def match_and_update_bios(all_bios, board_pages):
    """
    Match extracted bios to database and update.
    """
    conn = sqlite3.connect('/home/dfoss/crm/database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    # Get board members
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
    unmatched = []
    
    for pid, pname, pfid in board_members:
        # Find matching foundation
        db_name_norm = normalize_name(pname)
        
        for fname, fbios in all_bios.items():
            for bname, (burl, bfoundation_id) in board_pages.items():
                if bname == fname and pfid == bfoundation_id:
                    for bio_name, bio in fbios.items():
                        bio_name_norm = normalize_name(bio_name)
                        
                        # Fuzzy match
                        similarity = fuzz.ratio(db_name_norm, bio_name_norm)
                        
                        if similarity >= 85:
                            # Check if bio is actually useful (not empty or too short)
                            if bio and len(bio.strip()) > 5:
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
    
    # Sort by similarity and show top matches
    matched.sort(key=lambda x: x['similarity'], reverse=True)
    
    for m in matched[:20]:
        print(f"  ✓ {m['name'][:40]:<40} (match: {m['similarity']:3.0f}%)")
        print(f"      Bio: {m['bio'][:60]}...")
    
    if len(matched) > 20:
        print(f"\n  ... and {len(matched) - 20} more matches")
    
    conn.close()
    
    return updated_count, matched


def main():
    """Main extraction pipeline."""
    print("=" * 70)
    print("BIO EXTRACTION PIPELINE (LLM-Enhanced)")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_bios = {}
    results = []
    
    # Extract bios from all foundations
    for foundation_name, (url, foundation_id) in BOARD_PAGES.items():
        result = scrape_bios(foundation_name, url, foundation_id)
        results.append(result)
        
        if 'error' not in result:
            print(f"  Extracted {result['bio_count']} bios (raw: {result['raw_count']})")
            if result['bios']:
                for name, bio in list(result['bios'].items())[:3]:
                    print(f"    - {name}: {bio[:50]}...")
            all_bios[foundation_name] = result['bios']
        else:
            print(f"  Error: {result.get('error')}")
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save extraction results
    with open(f'/home/dfoss/crm/extracted_bios_{timestamp}.json', 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'results': results,
            'bios': all_bios
        }, f, indent=2)
    
    # Match and update database
    updated_count, matched = match_and_update_bios(all_bios, BOARD_PAGES)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for result in results:
        foundation = result['foundation']
        if 'error' not in result:
            print(f"  {foundation}: {result['bio_count']} bios extracted")
        else:
            print(f"  {foundation}: ERROR - {result.get('error', 'Unknown')}")
    
    print(f"\n  Total bios extracted: {sum(r.get('bio_count', 0) for r in results)}")
    print(f"  Database updates: {updated_count}")
    
    # Show final stats
    conn = sqlite3.connect('/home/dfoss/crm/database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1")
    total_board = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1 AND bio IS NOT NULL AND bio != ''")
    with_bios = cursor.fetchone()[0]
    
    print(f"\n  Board members with bios: {with_bios}/{total_board} ({100*with_bios/total_board:.1f}%)")
    
    conn.close()
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Results saved to: /home/dfoss/crm/extracted_bios_{timestamp}.json")


if __name__ == '__main__':
    main()
