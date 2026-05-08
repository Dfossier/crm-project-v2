#!/usr/bin/env python3
"""
Scrape board pages to extract actual board member names with better precision.
"""

import requests
from bs4 import BeautifulSoup
import json
import re

# Board pages to scrape
board_pages = [
    ("LSU Foundation", "https://www.lsufoundation.org/who-we-are/our-team/board-of-directors/index.php"),
    ("GNOF", "https://www.gnof.org/who-we-are/board-and-staff/"),
    ("BRAF", "https://www.braf.org/board-of-directors/"),
    ("CFNLA", "https://cfnla.org/board/"),
    ("BRF", "https://www.brfla.org/brf-board-and-leadership/"),
    ("IDF", "https://internationaldominicanfoundation.org/board-of-directors/"),
    ("SWLAC", "https://www.swlacharterfoundation.org/board-of-trustees/"),
    ("LSUHS", "https://www.lsuhsfoundation.org/your-foundation#board"),
    ("Pelican", "https://www.kenilworthacademy.org/board-of-directors"),
    ("Grambling", "https://lincolnprep.wildapricot.org/Board"),
    ("Caresouth", "https://www.caresouth.org/board-of-directors"),
    ("Hospice BR", "https://www.hospicebr.org/pages/board-of-directors"),
]

def extract_names_from_page(soup, url):
    """Extract actual person names from a page using smarter heuristics."""
    names = []
    bios = []
    
    # Strategy 1: Look for person cards/profiles
    for card in soup.find_all(['div', 'article'], class_=re.compile(r'(person|member|profile|card|board)', re.I)):
        name_elem = card.find(['h2', 'h3', 'h4', 'strong'])
        if name_elem:
            name = name_elem.get_text(strip=True)
            if is_likely_name(name):
                names.append(name)
        
        # Look for bio text in card
        for p in card.find_all('p'):
            txt = p.get_text(strip=True)
            if 20 < len(txt) < 500:
                bios.append(txt)
    
    # Strategy 2: Look for JSON-LD structured data
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'Person':
                name = data.get('name', '')
                if name:
                    names.append(name)
                    bio = data.get('description', '') or data.get('jobTitle', '')
                    if bio:
                        bios.append(bio)
        except:
            pass
    
    # Strategy 3: Look for li elements with names (common pattern)
    for li in soup.find_all('li'):
        txt = li.get_text(strip=True)
        # Filter out navigation-like text
        if is_likely_name(txt) and len(txt) < 100:
            names.append(txt)
    
    # Strategy 4: Look for patterns like "John Smith, MD" or "Jane Doe - Chair"
    text = soup.get_text()
    # Match "First Last, Title" or "First Last - Title" patterns
    pattern = r'\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z]\.?)+\s*,\s*[A-Za-z\s,]+'
    matches = re.findall(pattern, text)
    for match in matches:
        if len(match) < 100:
            names.append(match.strip())
    
    return list(set(names)), bios

def is_likely_name(text):
    """Check if text looks like a person's name."""
    if not text or len(text) < 3 or len(text) > 50:
        return False
    
    # Filter out common non-name words
    exclude = ['about', 'board', 'staff', 'contact', 'home', 'donate', 'give',
               'mission', 'vision', 'news', 'events', 'programs', 'services',
               'login', 'enroll', 'apply', 'career', 'opportunity', 'calendar',
               'meeting', 'literacy', 'schedule', 'appointment', 'magazine',
               'past', 'current', 'quality', 'job', 'grant', 'tax', 'donor']
    
    words = text.lower().split()
    if any(w in exclude for w in words):
        return False
    
    # Should have 2-4 words, starting with capitals
    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False
    
    # Check for name-like pattern (Capitalized words)
    capitals = sum(1 for w in words if w[0].isupper() and len(w) > 1)
    if capitals < 2:
        return False
    
    return True

def scrape_board_page(name, url):
    """Scrape a board page and extract member information."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return {'name': name, 'url': url, 'error': f'HTTP {response.status_code}'}
        
        soup = BeautifulSoup(response.content, 'html.parser')
        names, bios = extract_names_from_page(soup, url)
        
        # Filter names - remove duplicates and very short ones
        names = [n for n in names if len(n) > 3]
        
        return {
            'name': name,
            'url': url,
            'names': names[:20],  # Top 20 names
            'name_count': len(names),
            'bio_count': len(bios),
            'sample_bios': [b for b in bios if len(b) > 30][:3]
        }
        
    except Exception as e:
        return {'name': name, 'url': url, 'error': str(e)}

def main():
    results = []
    
    print("Scraping board pages...\n")
    
    for name, url in board_pages:
        print(f"[{name}] {url}")
        result = scrape_board_page(name, url)
        results.append(result)
        
        if 'error' not in result:
            print(f"  Found {result['name_count']} names")
            if result['names'][:3]:
                print(f"  Sample: {result['names'][:3]}")
    
    # Save results
    with open('/home/dfoss/crm/board_member_extraction.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_names = sum(r.get('name_count', 0) for r in results if 'error' not in r)
    print(f"\nTotal names extracted: {total_names}")
    
    for r in results:
        if 'error' not in r and r['name_count'] > 0:
            print(f"\n{r['name']}: {r['name_count']} names")
            for n in r['names'][:5]:
                print(f"  - {n}")
            if r.get('sample_bios'):
                print(f"  Bios: {r['sample_bios'][0][:100]}...")

if __name__ == '__main__':
    main()
