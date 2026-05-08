#!/usr/bin/env python3
"""
Expanded board member scraper - all foundations with board pages.
"""

import requests
from bs4 import BeautifulSoup
import json
import re

# All board pages from site tree extraction
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
    ("LSU Real Estate", "https://lsu.edu/bos/index.php"),
    ("Fore Kids", "https://www.pgatour.com/leaderboard"),
]

def extract_names_expanded(soup, url):
    """Expanded extraction with multiple strategies."""
    names = []
    bios = []
    
    # Strategy 1: img alt text
    for img in soup.find_all('img'):
        alt = img.get('alt', '') or ''
        if looks_like_name(alt):
            names.append(alt.strip())
    
    # Strategy 2: JSON-LD Person data
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if data.get('@type') == 'Person':
                    name = data.get('name', '')
                    if looks_like_name(name):
                        names.append(name)
                elif data.get('@type') == 'Organization':
                    members = data.get('member', [])
                    if isinstance(members, list):
                        for m in members:
                            if isinstance(m, dict) and m.get('@type') == 'Person':
                                name = m.get('name', '')
                                if looks_like_name(name):
                                    names.append(name)
        except:
            pass
    
    # Strategy 3: h3/h4 with names in cards
    for tag in soup.find_all(['h3', 'h4', 'strong']):
        txt = tag.get_text(strip=True)
        if looks_like_name(txt) and len(txt) < 60:
            names.append(txt)
    
    # Strategy 4: Look for name patterns in list items
    for li in soup.find_all('li'):
        txt = li.get_text(strip=True)
        # Match "Name" or "Name, Title"
        if 4 < len(txt) < 50 and looks_like_name(txt.split(',')[0]):
            names.append(txt.split(',')[0].strip())
    
    # Strategy 5: Pattern matching in text
    text = soup.get_text()
    patterns = [
        r"\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+[A-Z]\.?)+",  # "John Smith" or "John M. Smith"
        r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\s+(?:Jr\.?|Sr\.?|III?|IV?)",  # "John Smith Jr."
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            cleaned = str(match).replace('\n', ' ').strip()
            if looks_like_name(cleaned) and len(cleaned) < 50:
                names.append(cleaned)
    
    # Deduplicate
    names = list(set(names))
    # Clean up
    names = [n.strip().replace(' photo', '').replace('Photo', '').strip() for n in names]
    names = [n for n in names if len(n) > 3]
    
    return list(set(names)), bios

def looks_like_name(text):
    """Check if text looks like a person's name."""
    if not text or len(text) < 4 or len(text) > 50:
        return False
    
    # Exclude common words
    exclude = ['about', 'board', 'staff', 'contact', 'home', 'donate', 'give',
               'mission', 'vision', 'news', 'events', 'programs', 'services',
               'foundation', 'development', 'annual', 'report', 'financial',
               'statement', 'accessibility', 'privacy', 'policy', 'terms',
               'conditions', 'resources', 'forms', 'competitive', 'charitable',
               'giving', 'planned', 'city', 'stats', 'education', 'excellent',
               'economic', 'prosperity', 'space', 'rent', 'research', 'link',
               'partners', 'impact', 'retreat', 'lake', 'support', 'enrollment',
               'middle', 'school', 'volleyball', 'counselor', 'transportation',
               'dual', 'enrollment', 'partners', 'hearing', 'budget', 'quarter',
               'leadership', 'administration', 'history', 'traditions', 'visiting',
               'faculty', 'leaderboard', 'competition', 'zurich', 'classic',
               'new', 'orleans', 'university', 'view', 'academy', 'legal',
               'notices', 'policies', 'boardview', 'identity', 'account',
               'login', 'return', 'medical', 'minutes', 'category']
    
    words = text.lower().split()
    if any(w in exclude for w in words):
        return False
    
    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False
    
    # First two words should be capitalized
    if len(words) >= 2:
        if not (words[0][0].isupper() and words[1][0].isupper()):
            return False
    
    # Check for non-name characters
    if any(char in text for char in ['/', '|', '<', '>', '()', '[]', '#']):
        return False
    
    return True

def scrape_board_page(name, url):
    """Scrape a board page."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return {'name': name, 'url': url, 'error': f'HTTP {response.status_code}'}
        
        soup = BeautifulSoup(response.content, 'html.parser')
        names, bios = extract_names_expanded(soup, url)
        
        return {
            'name': name,
            'url': url,
            'names': names,
            'name_count': len(names),
            'bio_count': len(bios),
            'sample_bios': [b for b in bios if len(b) > 30][:3]
        }
        
    except Exception as e:
        return {'name': name, 'url': url, 'error': str(e)}

def main():
    results = []
    
    print("Scraping all board pages...\n")
    
    for name, url in board_pages:
        print(f"[{name}] {url}")
        result = scrape_board_page(name, url)
        results.append(result)
        
        if 'error' not in result:
            print(f"  Found {result['name_count']} names")
            if result['names'][:3]:
                print(f"  Sample: {result['names'][:3]}")
        else:
            print(f"  Error: {result.get('error')}")
    
    # Save results
    with open('/home/dfoss/crm/board_members_expanded.json', 'w') as f:
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

if __name__ == '__main__':
    main()
