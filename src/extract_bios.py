#!/usr/bin/env python3
"""
Extract bios from board pages for matched personnel.
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
    
    # Strategy 2: Name + title format (e.g., "Thomas Adamek - Founder, Stonehenge Capital")
    # Look for list items or paragraphs with name and title
    for element in soup.find_all(['li', 'p', 'div']):
        txt = element.get_text(strip=True)
        # Match patterns like "Name - Title" or "Name\nTitle"
        match = re.match(r'^([A-Z][A-Za-z]+(?:\s+[A-Z][a-z]+)+(?:,\s*[A-Z][a-z]+)?),?\s*(?:-|\n)\s*(.+)$', txt)
        if match:
            name = match.group(1).strip()
            title = match.group(2).strip()
            if 4 < len(name) < 60 and 5 < len(title) < 200:
                if name not in bios:
                    bios[name] = title
    
    # Strategy 3: Name + role with <br/> separator (e.g., CFNLA: "Lisa C. Cronin<br/>Chairman")
    for p in soup.find_all('p'):
        br = p.find('br')
        if br:
            # Get text before br (name)
            before = []
            for sib in br.previous_siblings:
                if isinstance(sib, str):
                    before.append(sib)
            name = ''.join(reversed(before)).strip()
            
            # Get text after br (role/title)
            after = []
            for sib in br.next_siblings:
                if isinstance(sib, str):
                    after.append(sib)
            role = ''.join(after).strip()
            
            if name and role and 4 < len(name) < 60:
                # Filter out non-person entries
                if role.lower() not in ['donate today', 'hours', 'monday', 'tuesday']:
                    if name not in bios:
                        bios[name] = role
    
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
    
    print("Extracting bios from board pages...\n")
    
    for name, (url, fid) in board_pages.items():
        print(f"[{name}] {url}")
        result = scrape_bios(name, url, fid)
        
        if 'error' not in result:
            print(f"  Found {result['bio_count']} bios")
            if result['bios']:
                for n, b in list(result['bios'].items())[:3]:
                    print(f"    {n}: {b[:80]}...")
            all_bios[name] = result['bios']
        else:
            print(f"  Error: {result.get('error')}")
    
    # Save bios
    with open('/home/dfoss/crm/extracted_bios.json', 'w') as f:
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
                            if updated_count <= 10:
                                print(f"  ✓ {pname}: {bio[:60]}...")
                            break
    
    conn.commit()
    conn.close()
    
    print(f"\n\nUpdated {updated_count} personnel with bios")

if __name__ == '__main__':
    main()
