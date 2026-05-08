#!/usr/bin/env python3
"""
Extract bios from board pages for matched personnel - V2 with improved patterns.
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import json
import re
from fuzzywuzzy import fuzz

# Board pages to extract bios from
board_pages = {
    "LSUHS": ("https://www.lsuhsfoundation.org/your-foundation#board", 26),
    "BRAF": ("https://www.braf.org/board-of-directors/", 9),
    "CFNLA": ("https://cfnla.org/board/", 19),
    "BRF": ("https://www.brfla.org/brf-board-and-leadership/", 20),
    "IDF": ("https://internationaldominicanfoundation.org/board-of-directors/", 21),
    "LSU Foundation": ("https://www.lsufoundation.org/who-we-are/our-team/board-of-directors/index.php", 4),
    "SWLAC": ("https://www.swlacharterfoundation.org/board-of-trustees/", 25),
}

def extract_bios(soup, url):
    """Extract person cards with bios or titles."""
    bios = {}
    
    # Strategy 1: Look for person cards with name + bio
    for card in soup.find_all(['div', 'article', 'section'], class_=re.compile(r'(person|member|profile|card|board|director)', re.I)):
        name = None
        bio = None
        
        # Get name from heading
        for tag in card.find_all(['h2', 'h3', 'h4', 'strong']):
            txt = tag.get_text(strip=True)
            if 4 < len(txt) < 60:
                name = txt
                break
        
        # Get bio from paragraph
        for p in card.find_all('p'):
            txt = p.get_text(strip=True)
            if name and 30 < len(txt) < 500:
                bio = txt
                break
        
        if name and bio:
            bios[name] = bio
    
    # Strategy 2: Name + role with <br/> + <em> pattern (CFNLA: <strong>Name</strong><br/><em>Role</em>)
    for p in soup.find_all('p'):
        strong = p.find('strong')
        br = p.find('br')
        em = p.find('em')
        
        if strong and br and em:
            name = strong.get_text(strip=True)
            role = em.get_text(strip=True)
            
            # Filter valid names
            if 4 < len(name) < 60 and name[0].isupper():
                # Skip non-person entries
                if name.lower() not in ['donate today', 'board of directors']:
                    if name not in bios:
                        bios[name] = role
    
    # Strategy 3: Table-based board (BRAF style: | Name | Role | Affiliation |)
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                name = cells[0].get_text(strip=True)
                role = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                affil = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                
                # Filter valid names
                if 4 < len(name) < 60 and name[0].isupper():
                    if name.lower() not in ['name', 'role', 'professional affiliation']:
                        bio = role
                        if affil:
                            bio += f", {affil}"
                        if name not in bios:
                            bios[name] = bio
    
    # Strategy 4: JSON-LD Person data with description
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'Person':
                name = data.get('name', '')
                bio = data.get('description', '') or data.get('jobTitle', '')
                if name and bio:
                    bios[name] = bio
        except:
            pass
    
    return bios

def scrape_bios(name, url, foundation_id):
    """Scrape bios from a board page."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return {'foundation': name, 'error': f'HTTP {response.status_code}'}
        
        soup = BeautifulSoup(response.content, 'html.parser')
        bios = extract_bios(soup, url)
        
        return {
            'foundation': name,
            'foundation_id': foundation_id,
            'bios': bios,
            'bio_count': len(bios)
        }
        
    except Exception as e:
        return {'foundation': name, 'error': str(e)}

def main():
    all_bios = {}
    
    print("Extracting bios from board pages (V2)...\n")
    
    for name, (url, fid) in board_pages.items():
        print(f"[{name}] {url}")
        result = scrape_bios(name, url, fid)
        
        if 'error' not in result:
            print(f"  Found {result['bio_count']} bios")
            if result['bios']:
                for n, b in list(result['bios'].items())[:5]:
                    print(f"    {n}: {b[:70]}...")
            all_bios[name] = result['bios']
        else:
            print(f"  Error: {result.get('error')}")
    
    # Save bios
    with open('/home/dfoss/crm/extracted_bios_v2.json', 'w') as f:
        json.dump(all_bios, f, indent=2)
    
    # Update database
    conn = sqlite3.connect('/home/dfoss/crm/database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    # Get board members
    cursor.execute("""
        SELECT id, name, foundation_id 
        FROM personnel_990 
        WHERE is_board_member = 1
    """)
    board_members = cursor.fetchall()
    
    print("\n" + "=" * 60)
    print("MATCHING BIOS TO DATABASE")
    print("=" * 60)
    
    updated_count = 0
    for pid, pname, pfid in board_members:
        # Find matching foundation
        for fname, fbios in all_bios.items():
            for fid, fn in board_pages.items():
                if fid == fname and pfid == fn[1]:
                    # Normalize names
                    db_name = pname.upper().replace('MD', '').replace('DR', '').replace('PHD', '').strip()
                    
                    for bio_name, bio in fbios.items():
                        bio_name_norm = bio_name.upper().replace('MD', '').replace('DR', '').replace('PHD', '').strip()
                        
                        if fuzz.ratio(db_name, bio_name_norm) >= 85:
                            cursor.execute("""
                                UPDATE personnel_990 
                                SET bio = ? 
                                WHERE id = ?
                            """, (bio, pid))
                            updated_count += 1
                            if updated_count <= 15:
                                print(f"  ✓ {pname}: {bio[:50]}...")
                            break
    
    conn.commit()
    conn.close()
    
    print(f"\n\nUpdated {updated_count} personnel with bios")
    
    # Show stats
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1 AND bio IS NOT NULL AND bio != ''")
    total_with_bios = cursor.fetchone()[0]
    print(f"Total board members with bios: {total_with_bios}")

if __name__ == '__main__':
    main()
