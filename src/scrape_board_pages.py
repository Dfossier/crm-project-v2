#!/usr/bin/env python3
"""
Scrape board pages from foundations to extract board member names.
"""

import requests
from bs4 import BeautifulSoup
import json

# Board pages found
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

def scrape_board_page(name, url):
    """Extract board member names from a page."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return {'name': name, 'url': url, 'error': f'HTTP {response.status_code}'}
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for names (people usually have last names with caps)
        # Strategy: find text blocks that look like names
        names = []
        bios = []
        
        # Look for common patterns:
        # 1. List items with names
        # 2. Cards with person info
        # 3. Tables with names
        
        # Try to find name-like patterns
        text = soup.get_text()
        
        # Look for structured data
        for element in soup.find_all(['h2', 'h3', 'h4', 'p', 'li']):
            txt = element.get_text(strip=True)
            # Skip very short or very long text
            if 3 < len(txt) < 200:
                # Check if it looks like a person name
                words = txt.split()
                if len(words) >= 2 and len(words) <= 4:
                    # Check for capital first letters (names)
                    capitals = sum(1 for w in words if w[0].isupper() if w)
                    if capitals >= 2:
                        names.append(txt)
        
        # Look for bio text
        for p in soup.find_all('p'):
            txt = p.get_text(strip=True)
            if 20 < len(txt) < 500:
                bios.append(txt)
        
        return {
            'name': name,
            'url': url,
            'names_found': len(set(names)),
            'sample_names': list(set(names))[:5],
            'bio_count': len(bios),
            'has_bios': any(len(b) > 50 for b in bios)
        }
        
    except Exception as e:
        return {'name': name, 'url': url, 'error': str(e)}

def main():
    results = []
    for name, url in board_pages:
        print(f"\n[{name}] {url}")
        result = scrape_board_page(name, url)
        results.append(result)
        
        if 'error' not in result:
            print(f"  Names found: {result['names_found']}")
            if result['sample_names']:
                print(f"  Samples: {result['sample_names'][:3]}")
            print(f"  Has bios: {result['has_bios']}")
    
    # Save results
    with open('/home/dfoss/crm/board_scraping_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    with_names = [r for r in results if 'error' not in r and r.get('names_found', 0) > 0]
    with_bios = [r for r in results if 'error' not in r and r.get('has_bios', False)]
    
    print(f"\nPages with names: {len(with_names)}/{len(results)}")
    print(f"Pages with bios: {len(with_bios)}/{len(results)}")
    
    for r in with_names:
        print(f"\n{r['name']}: {r['names_found']} names")
        for n in r['sample_names'][:3]:
            print(f"  - {n}")

if __name__ == '__main__':
    main()
