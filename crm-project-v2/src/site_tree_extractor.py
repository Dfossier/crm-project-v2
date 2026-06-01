#!/usr/bin/env python3
"""
Extract site tree/navigation from foundation websites.
Looks for About Us, Board, Leadership, Team sections.
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urlparse, urljoin

def extract_site_tree(url):
    """Extract navigation structure from a website."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return {'error': f'HTTP {response.status_code}'}
        
        soup = BeautifulSoup(response.content, 'html.parser')
        base_url = url.rstrip('/')
        
        # Find all navigation elements
        nav_elements = []
        
        # Look for nav tags
        for nav in soup.find_all(['nav', 'header', 'div']):
            if nav.get('class'):
                class_str = ' '.join(nav.get('class', [])).lower()
                if 'nav' in class_str or 'menu' in class_str or 'header' in class_str:
                    links = nav.find_all('a', href=True)
                    for link in links:
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        if href and text:
                            # Resolve relative URLs
                            full_url = urljoin(base_url, href) if not href.startswith('http') else href
                            nav_elements.append({
                                'text': text,
                                'url': full_url,
                                'type': 'nav'
                            })
        
        # Also scan all links on page
        all_links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            if href and text and href.startswith('/'):
                full_url = urljoin(base_url, href)
                all_links.append({
                    'text': text,
                    'url': full_url
                })
        
        # Categorize links
        about_links = []
        board_links = []
        leadership_links = []
        team_links = []
        other_links = []
        
        link_keywords = {
            'about': ['about', 'our story', 'mission', 'who we are', 'about us'],
            'board': ['board', 'directors', 'governance', 'board of directors'],
            'leadership': ['leadership', 'executive', 'administra', 'staff'],
            'team': ['team', 'our team']
        }
        
        for item in nav_elements + all_links:
            text_lower = item['text'].lower()
            url_lower = item['url'].lower()
            combined = f"{text_lower} {url_lower}"
            
            if any(kw in combined for kw in link_keywords['about']):
                about_links.append(item)
            elif any(kw in combined for kw in link_keywords['board']):
                board_links.append(item)
            elif any(kw in combined for kw in link_keywords['leadership']):
                leadership_links.append(item)
            elif any(kw in combined for kw in link_keywords['team']):
                team_links.append(item)
            else:
                other_links.append(item)
        
        return {
            'url': url,
            'about': about_links[:5],  # Top 5
            'board': board_links[:5],
            'leadership': leadership_links[:5],
            'team': team_links[:5],
            'all_links': len(nav_elements + all_links),
            'nav_elements': len(nav_elements)
        }
        
    except Exception as e:
        return {'error': str(e)}

def main():
    # Load foundations from database
    conn = sqlite3.connect('/home/dfoss/crm/database/louisiana_foundations.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, website 
        FROM foundations 
        WHERE website IS NOT NULL AND website != '' AND website LIKE 'http%'
    ''')
    foundations = cursor.fetchall()
    conn.close()
    
    results = []
    for fid, name, website in foundations:
        print(f"\n[{fid}] {name}: {website}")
        tree = extract_site_tree(website)
        tree['foundation_id'] = fid
        tree['foundation_name'] = name
        results.append(tree)
        
        # Print findings
        if 'error' not in tree:
            if tree['board']:
                print(f"  BOARD: {tree['board']}")
            if tree['about']:
                print(f"  ABOUT: {tree['about']}")
            if tree['leadership']:
                print(f"  LEADERSHIP: {tree['leadership']}")
    
    # Save results
    with open('/home/dfoss/crm/foundation_site_trees.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n\nSaved {len(results)} site trees to foundation_site_trees.json")
    
    # Summary
    board_count = sum(1 for r in results if 'error' not in r and r.get('board'))
    about_count = sum(1 for r in results if 'error' not in r and r.get('about'))
    print(f"\nSummary:")
    print(f"  Found board pages: {board_count}/{len(results)}")
    print(f"  Found about pages: {about_count}/{len(results)}")

if __name__ == '__main__':
    main()
