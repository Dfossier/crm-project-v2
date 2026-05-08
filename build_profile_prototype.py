#!/usr/bin/env python3
"""
Profile Building Prototype
Test building a comprehensive profile for Jason Freyou from CF Acadiana
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import time
import re
import json

def scrape_foundation_bio(website, person_name):
    """Try to find bio on foundation website"""
    print(f"\n🔍 Scrape website: {website}")
    
    try:
        response = requests.get(website, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        bio_text = []
        
        # Strategy 1: Look for name on page
        for p in soup.find_all(['p', 'div', 'section', 'h3', 'h4']):
            p_text = p.get_text().strip()
            # Normalize name (remove title prefixes)
            norm_name = person_name.lower().replace('dr ', '').replace('jr', '').replace('sr', '')
            if norm_name in p_text.lower() and len(p_text) > 30:
                bio_text.append(p_text[:400])
        
        # Strategy 2: Look for board/leadership pages
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').lower()
            if 'board' in href or 'leadership' in href or 'team' in href or 'governance' in href:
                full_url = website.rstrip('/') + '/' + href.lstrip('/')
                try:
                    board_response = requests.get(full_url, timeout=10)
                    board_soup = BeautifulSoup(board_response.text, 'html.parser')
                    
                    for p in board_soup.find_all(['p', 'div', 'span']):
                        p_text = p.get_text().strip()
                        if norm_name in p_text.lower() and len(p_text) > 20:
                            bio_text.append(p_text[:300])
                except Exception as e:
                    pass
        
        # Strategy 3: Search for "About" pages
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').lower()
            if 'about' in href:
                full_url = website.rstrip('/') + '/' + href.lstrip('/')
                try:
                    about_response = requests.get(full_url, timeout=10)
                    about_soup = BeautifulSoup(about_response.text, 'html.parser')
                    
                    for p in about_soup.find_all(['p', 'div']):
                        p_text = p.get_text().strip()
                        if norm_name in p_text.lower() and len(p_text) > 20:
                            bio_text.append(p_text[:300])
                except:
                    pass
        
        return '\n\n'.join(set(bio_text)) if bio_text else "No bio found on website"
    
    except Exception as e:
        return f"Error scraping: {e}"


def search_news_mentions(name, location):
    """Search for news articles"""
    print(f"\n🔍 Search news for: {name} in {location}")
    
    # Normalize name for search
    clean_name = name.replace('DR ', '').replace('JR', '').replace('SR', '')
    query = f'{clean_name} {location}'
    
    try:
        # Use DuckDuckGo
        url = f"https://duckduckgo.com/?q={requests.utils.quote(query)}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        articles = []
        for result in soup.find_all(['article', 'div'], class_=['result', 'result__a']):
            title_tag = result.find('a', class_='result__a') or result.find('h2')
            snippet_tag = result.find('span', class_='result__snippet') or result.find('a', class_='result__s')
            
            if title_tag:
                articles.append({
                    'title': title_tag.get_text().strip()[:80],
                    'snippet': snippet_tag.get_text().strip()[:150] if snippet_tag else '',
                    'url': title_tag.get('href', '')
                })
        
        # Filter for relevant results
        relevant = [a for a in articles if location.lower() in a['title'].lower() or location.lower() in a['snippet'].lower()]
        return relevant[:5] if relevant else articles[:3]
    
    except Exception as e:
        print(f"News search error: {e}")
        return []


def extract_linkedin_info(linkedin_url):
    """Extract info from LinkedIn profile"""
    if not linkedin_url:
        return {}
    
    print(f"\n🔍 Checking LinkedIn: {linkedin_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(linkedin_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            info = {}
            
            # Try various selectors
            name_elem = soup.find('h1', {'class': lambda x: x and 'text-display' in x})
            if name_elem:
                info['display_name'] = name_elem.get_text().strip()
            
            headline = soup.find('h2', {'class': lambda x: x and 'text-body' in x})
            if headline:
                info['headline'] = headline.get_text().strip()
            
            location_elem = soup.find('span', {'class': lambda x: x and 'text-body' in x})
            if location_elem:
                info['location'] = location_elem.get_text().strip()
            
            # Try to find experience section
            experience = soup.find_all('div', {'class': lambda x: x and 'phr-profile-section' in x})
            if experience:
                info['has_experience_section'] = True
            
            return info if info else {"note": "LinkedIn requires login for full data"}
        else:
            return {"note": f"LinkedIn returned {response.status_code}"}
    
    except Exception as e:
        return {"note": f"Error: {e}"}


def verify_location(linkedin_location, foundation_city):
    """Check if LinkedIn location matches foundation city"""
    if not linkedin_location or not foundation_city:
        return "Unknown"
    
    if foundation_city.lower() in linkedin_location.lower():
        return "✓ Verified"
    elif "louisiana" in linkedin_location.lower():
        return "✓ Louisiana match"
    else:
        return f"✗ Mismatch: {linkedin_location}"


def build_profile(person_name, title, website, linkedin_url, foundation_name, city):
    """Build complete profile"""
    print("\n" + "="*60)
    print(f"BUILDING PROFILE FOR: {person_name}")
    print(f"Title: {title}")
    print(f"Foundation: {foundation_name}")
    print(f"City: {city}")
    print("="*60)
    
    profile = {
        'name': person_name,
        'title': title,
        'foundation': foundation_name,
        'city': city,
        'linkedin_url': linkedin_url,
        'website_bio': None,
        'news_mentions': [],
        'linkedin_info': {},
        'location_verified': None,
        'confidence_score': 0
    }
    
    # 1. Website bio
    profile['website_bio'] = scrape_foundation_bio(website, person_name)
    print(f"\n📝 Website Bio ({len(profile['website_bio'])} chars):")
    print(profile['website_bio'][:600] + ('...' if len(profile['website_bio']) > 600 else ''))
    
    # 2. News search
    time.sleep(2)
    profile['news_mentions'] = search_news_mentions(person_name, city)
    print(f"\n📰 News Mentions: {len(profile['news_mentions'])} found")
    for article in profile['news_mentions']:
        print(f"  • {article['title'][:50]}...")
        if article['snippet']:
            print(f"    {article['snippet'][:80]}...")
    
    # 3. LinkedIn
    time.sleep(2)
    profile['linkedin_info'] = extract_linkedin_info(linkedin_url)
    print(f"\n💼 LinkedIn Info:")
    for k, v in profile['linkedin_info'].items():
        print(f"  {k}: {v[:100] if len(str(v)) > 100 else v}")
    
    # 4. Location verification
    linkedin_loc = profile['linkedin_info'].get('location', '')
    profile['location_verified'] = verify_location(linkedin_loc, city)
    print(f"\n📍 Location Verification: {profile['location_verified']}")
    
    # 5. Calculate confidence score
    score = 0
    if len(profile['website_bio']) > 50:
        score += 0.3
    if len(profile['news_mentions']) > 0:
        score += 0.3
    if profile['location_verified'].startswith('✓'):
        score += 0.2
    if profile['linkedin_info'] and 'note' not in profile['linkedin_info']:
        score += 0.2
    
    profile['confidence_score'] = score
    
    return profile


def save_profile(profile):
    """Save profile to JSON file"""
    filename = f"profile_{profile['name'].lower().replace(' ', '_').replace('.', '')}.json"
    with open(filename, 'w') as f:
        json.dump(profile, f, indent=2, default=str)
    print(f"\n✅ Profile saved to {filename}")


if __name__ == "__main__":
    # Test with Jason Freyou from CF Acadiana
    profile = build_profile(
        person_name="Jason Freyou",
        title="Chair",
        website="https://www.cfacadiana.org",
        linkedin_url="https://www.linkedin.com/in/jason-p-freyou-ba447226",
        foundation_name="Community Foundation Of Acadiana",
        city="Lafayette"
    )
    
    print("\n" + "="*60)
    print("FINAL PROFILE SUMMARY")
    print("="*60)
    print(f"\nName: {profile['name']}")
    print(f"Title: {profile['title']}")
    print(f"Foundation: {profile['foundation']}")
    print(f"City: {profile['city']}")
    print(f"Confidence Score: {profile['confidence_score']:.1f}/1.0")
    print(f"Location Verified: {profile['location_verified']}")
    print(f"Website Bio: {'Found' if len(profile['website_bio']) > 50 else 'Not found'} ({len(profile['website_bio'])} chars)")
    print(f"News Mentions: {len(profile['news_mentions'])}")
    print(f"LinkedIn Data: {'Yes' if profile['linkedin_info'] and 'note' not in profile['linkedin_info'] else 'No/Blocked'}")
    
    save_profile(profile)
