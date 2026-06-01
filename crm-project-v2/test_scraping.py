#!/usr/bin/env python3
"""Test scraping GNFO board page"""

import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Try GNFO board page
website = "https://www.gnof.org/who-we-are/board-and-staff/"
print(f"Scraping: {website}")

try:
    response = requests.get(website, headers=headers, timeout=15)
    print(f"Status: {response.status_code}")
    print(f"Content length: {len(response.text)}")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Look for people names and bios
    print("\nLooking for bios...")
    
    # Find all paragraphs and divs
    elements = soup.find_all(['p', 'div', 'section', 'h3', 'h4'])
    
    bio_count = 0
    for elem in elements:
        text = elem.get_text().strip()
        # Filter for bio-like content
        if 50 < len(text) < 300:
            # Skip navigation/boilerplate
            if any(x in text.lower() for x in ['sign in', 'login', 'subscribe', 'contact us', 'follow us']):
                continue
            
            bio_count += 1
            if bio_count <= 10:
                print(f"\n[{bio_count}] {text[:150]}...")
    
    print(f"\nTotal potential bios: {bio_count}")
    
    # Show structure
    print("\nPage structure:")
    for tag in ['h1', 'h2', 'h3', 'h4']:
        count = len(soup.find_all(tag))
        if count > 0:
            print(f"  {tag}: {count}")
    
except Exception as e:
    print(f"Error: {e}")
