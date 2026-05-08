#!/usr/bin/env python3
"""
Improved board member scraper - more precise name extraction.
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

def extract_names_v2(soup, url):
    """Extract person names with stricter heuristics."""
    names = []
    bios = []
    
    # Strategy 1: Look for img alt text with names (most reliable)
    for img in soup.find_all('img'):
        alt = img.get('alt', '') or ''
        if is_strict_name(alt):
            names.append(alt.strip())
    
    # Strategy 2: JSON-LD Person data (very reliable)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if data.get('@type') == 'Person':
                    name = data.get('name', '')
                    if is_strict_name(name):
                        names.append(name)
                        bio = data.get('description', '') or data.get('jobTitle', '')
                        if bio:
                            bios.append(bio)
                elif data.get('@type') == 'Organization':
                    # Look for member
                    members = data.get('member', [])
                    if isinstance(members, list):
                        for m in members:
                            if isinstance(m, dict) and m.get('@type') == 'Person':
                                name = m.get('name', '')
                                if is_strict_name(name):
                                    names.append(name)
        except:
            pass
    
    # Strategy 3: Person cards with specific patterns
    for div in soup.find_all(['div', 'article'], class_=re.compile(r'(person|member|board|profile|card|team)', re.I)):
        # Look for strong/h2/h3 with a name
        for tag in div.find_all(['strong', 'h2', 'h3', 'h4']):
            txt = tag.get_text(strip=True)
            if is_strict_name(txt) and len(txt) < 60:
                names.append(txt)
                # Look for bio in same div
                for p in div.find_all('p'):
                    ptxt = p.get_text(strip=True)
                    if 30 < len(ptxt) < 300:
                        bios.append(ptxt)
    
    # Strategy 4: Pattern "Name, Role" or "Name - Role"
    text = soup.get_text()
    # Match patterns like "John Smith, MD" or "Jane Doe, Chair" or "John Smith - VP"
    patterns = [
        r"\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+[A-Z]\.?)+\s*,\s*(?:Chair|Vice.?Chair|Secretary|Treasurer|Trustee|Director|Member|MD|DDS|DVM|PhD|Esq|President|CEO|CFO)",
        r"\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+[A-Z]\.?)+\s*-\s*(?:Chair|Vice.?Chair|Secretary|Treasurer|Trustee|Director|Member|President|CEO)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # Extract just the name part
            name_part = re.split(r'[,\-]', match)[0].strip()
            if is_strict_name(name_part):
                names.append(name_part)
    
    # Deduplicate and return
    names = list(set(names))
    return names, bios

def is_strict_name(text):
    """Stricter name validation."""
    if not text or len(text) < 4 or len(text) > 50:
        return False
    
    # Exclude common words that might slip through
    exclude = ['about', 'board', 'staff', 'contact', 'home', 'donate', 'give',
               'mission', 'vision', 'news', 'events', 'programs', 'services',
               'login', 'enroll', 'apply', 'career', 'opportunity', 'calendar',
               'meeting', 'literacy', 'schedule', 'appointment', 'magazine',
               'past', 'current', 'quality', 'job', 'grant', 'tax', 'donor',
               'foundation', 'development', 'annual', 'report', 'financial',
               'statement', 'accessibility', 'privacy', 'policy', 'terms',
               'conditions', 'resources', 'forms', 'competitive', 'charitable',
               'giving', 'planned', 'city', 'stats', 'education', 'excellent',
               'economic', 'prosperity', 'space', 'rent', 'forms', 'why',
               'research', 'shreveport', 'next', 'collaboration', 'link',
               'entrepreneur', 'accelerator', 'annual', 'budget', 'hearing',
               'enrollment', 'middle', 'school', 'volleyball', 'counselor',
               'bullying', 'transportation', 'dual', 'enrollment', 'partners',
               'impact', 'retreat', 'quarters', 'lake', 'bereavement', 'support',
               'nondiscrimination', 'policy', 'privacy']
    
    words = text.lower().split()
    if any(w in exclude for w in words):
        return False
    
    # Should have 2-4 words
    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False
    
    # First two words should be capitalized (first and last name)
    if len(words) >= 2:
        if not (words[0][0].isupper() and words[1][0].isupper()):
            return False
    
    # Check for common non-name patterns
    if any(char in text for char in ['/', '|', '<', '>', '()', '[]']):
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
        names, bios = extract_names_v2(soup, url)
        
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
    
    print("Scraping board pages (v2 - improved extraction)...\n")
    
    for name, url in board_pages:
        print(f"[{name}] {url}")
        result = scrape_board_page(name, url)
        results.append(result)
        
        if 'error' not in result:
            print(f"  Found {result['name_count']} names")
            if result['names'][:3]:
                print(f"  Sample: {result['names'][:3]}")
    
    # Save results
    with open('/home/dfoss/crm/board_members_v2.json', 'w') as f:
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
