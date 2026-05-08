#!/usr/bin/env python3
"""
Robust bio extraction pipeline - V3.
Handles diverse HTML structures with multiple strategies.
"""

import sqlite3
import json
import re
import requests
from datetime import datetime
from fuzzywuzzy import fuzz
from bs4 import BeautifulSoup

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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}

def fetch_page(url, max_retries=3):
    """Fetch page with retry logic."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            
            # Check for Cloudflare block
            if response.status_code == 200:
                if 'cloudflare' in response.text.lower() or 'blocked' in response.text.lower():
                    print(f"    Cloudflare block detected (attempt {attempt + 1})")
                    continue
                return response.content
            
            if attempt < max_retries - 1:
                print(f"    Retry {attempt + 1}/{max_retries} (HTTP {response.status_code})")
        except Exception as e:
            print(f"    Error attempt {attempt + 1}: {e}")
    
    return None


def extract_bios_from_soup(soup):
    """
    Extract bios using multiple strategies on BeautifulSoup parsed HTML.
    """
    bios = {}
    
    # Strategy 1: Table format (| Name | Role | Affiliation |)
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                name = cells[0].get_text(strip=True)
                role = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                affil = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                
                # Filter valid entries
                if 4 < len(name) < 60 and name[0].isupper():
                    exclude_terms = ['name', 'role', 'professional affiliation', 'cookie', 'duration', 'description']
                    if name.lower() not in exclude_terms:
                        bio = role
                        if affil:
                            bio += f", {affil}"
                        if name not in bios:
                            bios[name] = bio
    
    # Strategy 2: Strong/em pattern (<strong>Name</strong><br/><em>Role</em>)
    for p in soup.find_all('p'):
        strong = p.find('strong')
        br = p.find('br')
        em = p.find('em')
        
        if strong and br and em:
            name = strong.get_text(strip=True)
            role = em.get_text(strip=True)
            
            if 4 < len(name) < 60 and name[0].isupper():
                if name.lower() not in ['donate today', 'board of directors']:
                    if name not in bios:
                        bios[name] = role
    
    # Strategy 3: Strong tag followed by text (name + role in same element)
    for strong in soup.find_all('strong'):
        txt = strong.get_text(strip=True)
        if 8 < len(txt) < 60 and txt[0].isupper():
            # Check if next sibling has role
            next_elem = strong.find_next_sibling()
            if next_elem and next_elem.name in ['em', 'span', 'small']:
                role = next_elem.get_text(strip=True)
                if role and 3 < len(role) < 100:
                    if txt not in bios:
                        bios[txt] = role
    
    # Strategy 4: Paragraph with line breaks (name\nrole)
    for p in soup.find_all('p'):
        br = p.find('br')
        if br:
            # Get all text and split by br position
            full_text = p.get_text()
            parts = full_text.split('\n')
            parts = [p.strip() for p in parts if p.strip()]
            
            if len(parts) >= 2:
                name = parts[0]
                role = parts[1]
                
                if 4 < len(name) < 60 and name[0].isupper():
                    if name.lower() not in ['board of directors', 'donate today', 'hours', 'follow']:
                        if name not in bios:
                            bios[name] = role
    
    # Strategy 5: List items with separator (Name - Role)
    for li in soup.find_all('li'):
        txt = li.get_text(strip=True)
        
        # Try different separators
        for sep in [' - ', ' – ', ' | ', ' • ']:
            if sep in txt:
                parts = txt.split(sep, 1)
                if len(parts) == 2:
                    name = parts[0].strip()
                    role = parts[1].strip()
                    
                    if 4 < len(name) < 60 and 5 < len(role) < 200:
                        if name[0].isupper():
                            if name not in bios:
                                bios[name] = role
                break
    
    # Strategy 6: JSON-LD Person data
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'Person':
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
    
    # Strategy 7: Card-based layout (divs with person/member class)
    for card in soup.find_all(['div', 'article'], class_=re.compile(r'(person|member|profile|card|board|director)', re.I)):
        name = None
        bio = None
        
        # Get name from heading
        for tag in card.find_all(['h2', 'h3', 'h4', 'strong']):
            txt = tag.get_text(strip=True)
            if 4 < len(txt) < 60:
                name = txt
                break
        
        # Get bio from paragraph
        if name:
            for p in card.find_all('p'):
                txt = p.get_text(strip=True)
                if 30 < len(txt) < 500:
                    bio = txt
                    break
        
        if name and bio:
            if name not in bios:
                bios[name] = bio
    
    # Filter out obvious non-person entries
    filtered = {}
    for name, bio in bios.items():
        # Skip if name looks like non-person
        if re.match(r'^\d+\s*$', name):  # Just numbers
            continue
        if re.match(r'^https?://', name):  # URL
            continue
        if re.match(r'^\d+\s*[A-Z][a-z]+\s*(St|Street|Ave|Avenue)', name, re.I):  # Address
            continue
        
        # Skip if bio is too short or looks like navigation
        if len(bio) < 3:
            continue
        if re.search(r'(hours?|phone|email|contact|follow|donate)', bio, re.I):
            continue
        
        filtered[name] = bio
    
    return filtered


def scrape_bios(foundation_name, url, foundation_id):
    """Scrape bios from a board page."""
    print(f"\n[{foundation_name}]")
    print(f"  URL: {url}")
    
    html = fetch_page(url)
    
    if html is None:
        return {'foundation': foundation_name, 'error': 'Failed to fetch page'}
    
    # Check for Cloudflare block
    if b'cloudflare' in html.lower() or b'blocked' in html.lower():
        return {'foundation': foundation_name, 'error': 'Cloudflare block'}
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        bios = extract_bios_from_soup(soup)
        
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
    name = re.sub(r',\s*Esq\.', '', name, flags=re.I)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def match_and_update_bios(all_bios, board_pages):
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
            for bname, (burl, bfoundation_id) in board_pages.items():
                if bname == fname and pfid == bfoundation_id:
                    for bio_name, bio in fbios.items():
                        bio_name_norm = normalize_name(bio_name)
                        similarity = fuzz.ratio(db_name_norm, bio_name_norm)
                        
                        if similarity >= 85 and bio and len(bio.strip()) > 5:
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
    print("BIO EXTRACTION PIPELINE V3")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_bios = {}
    results = []
    
    for foundation_name, (url, foundation_id) in BOARD_PAGES.items():
        result = scrape_bios(foundation_name, url, foundation_id)
        results.append(result)
        
        if 'error' not in result:
            print(f"  Extracted {result['bio_count']} bios")
            if result['bios']:
                for name, bio in list(result['bios'].items())[:3]:
                    print(f"    - {name}: {bio[:50]}...")
            all_bios[foundation_name] = result['bios']
        else:
            print(f"  Error: {result.get('error')}")
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with open(f'/home/dfoss/crm/extracted_bios_{timestamp}.json', 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'results': results,
            'bios': all_bios
        }, f, indent=2)
    
    # Match and update
    updated_count, matched = match_and_update_bios(all_bios, BOARD_PAGES)
    
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
    print(f"Results saved to: /home/dfoss/crm/extracted_bios_{timestamp}.json")


if __name__ == '__main__':
    main()
