#!/usr/bin/env python3
"""
Bio Enrichment System for Louisiana Foundations CRM
Extracts biographical data from foundation websites and stores in personnel_profiles

OPTIMIZED VERSION - fixes:
- Proper User-Agent headers
- Website caching (don't re-download same foundation)
- Only check specific board/leadership paths
- Faster regex-based name matching
- Reduced timeouts
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
import logging
import json
import os

# Setup logging
logging.basicConfig(
    filename='bio_enrichment.log',
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)

# Headers to avoid 403 blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# Cache directory
CACHE_DIR = '/tmp/crm_website_cache'
os.makedirs(CACHE_DIR, exist_ok=True)


def normalize_name(name):
    """Normalize name for searching - remove titles and suffixes"""
    if not name:
        return ""
    
    name = name.lower()
    name = re.sub(r'^(dr|mr|mrs|ms|phd|md|edd|ed|rev|fr|sr|br)\s*', '', name)
    name = re.sub(r'\s*(jr|sr|ii|iii|iv|v)$', '', name)
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'[-]', ' ', name)
    
    return name.strip()


def get_cache_key(url):
    """Generate cache key for URL"""
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()


def get_cached_html(url):
    """Get cached HTML if available"""
    cache_key = get_cache_key(url)
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.html")
    
    if os.path.exists(cache_path):
        # Check age (max 1 day)
        age = time.time() - os.path.getmtime(cache_path)
        if age < 86400:  # 24 hours
            with open(cache_path, 'r') as f:
                return f.read()
    return None


def save_to_cache(url, html):
    """Save HTML to cache"""
    cache_key = get_cache_key(url)
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.html")
    with open(cache_path, 'w') as f:
        f.write(html)


def fetch_html(url, timeout=10):
    """Fetch HTML with caching"""
    # Try cache first
    cached = get_cached_html(url)
    if cached:
        logging.info(f"Cache hit: {url}")
        return cached, "Cache"
    
    # Fetch from web
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        html = response.text
        save_to_cache(url, html)
        return html, f"Status {response.status_code}"
    except requests.exceptions.Timeout:
        return None, "Timeout"
    except requests.exceptions.ConnectionError:
        return None, "Connection Error"
    except Exception as e:
        return None, f"Error: {e}"


def scrape_website_bio(website, person_name):
    """Extract bio from foundation website"""
    if not website:
        return None, "No website"
    
    logging.info(f"Scraping {website} for {person_name}")
    
    # Normalize name
    norm_name = normalize_name(person_name)
    name_parts = [p for p in norm_name.split() if len(p) > 3]  # Only meaningful parts
    
    if not name_parts:
        return None, "Name too short"
    
    # Fetch HTML (with caching)
    html, status = fetch_html(website)
    if not html:
        return None, status
    
    soup = BeautifulSoup(html, 'html.parser')
    bio_paragraphs = []
    
    # Strategy 1: Search main page for name mentions
    text = soup.get_text()
    
    # Quick check: does name appear anywhere?
    name_found = any(part in text.lower() for part in name_parts)
    if not name_found:
        return None, "Name not found on page"
    
    # Find paragraphs containing name
    for p in soup.find_all(['p', 'div', 'section', 'h3', 'h4']):
        p_text = p.get_text().strip()
        if not (50 < len(p_text) < 400):
            continue
        
        # Check if any name part appears
        for part in name_parts:
            if part in p_text.lower():
                bio_paragraphs.append(p_text)
                break
    
    # Strategy 2: Check known board/leadership paths
    board_paths = [
        '/board', '/board-of-directors', '/leadership', '/our-team',
        '/about/board', '/about/leadership', '/governance', '/who-we-are/board-and-staff/',
        '/board-and-staff', '/team', '/about-us'
    ]
    
    for path in board_paths:
        board_url = website.rstrip('/') + path
        html, _ = fetch_html(board_url, timeout=8)
        
        if html:
            board_soup = BeautifulSoup(html, 'html.parser')
            
            for p in board_soup.find_all(['p', 'div', 'h3', 'h4']):
                p_text = p.get_text().strip()
                if not (30 < len(p_text) < 400):
                    continue
                
                for part in name_parts:
                    if part in p_text.lower():
                        bio_paragraphs.append(f"[{path}] {p_text}")
                        break
    
    # Deduplicate and return
    unique_bios = list(set(bio_paragraphs))
    
    if not unique_bios:
        return None, "No bio found"
    
    return '\n\n'.join(unique_bios[:3]), "Scraped"


def search_news(person_name, city):
    """Search for news mentions using DuckDuckGo"""
    if not person_name or not city:
        return [], "Missing data"
    
    norm_name = normalize_name(person_name)
    query = f'{norm_name} {city}'
    
    try:
        url = f"https://duckduckgo.com/?q={requests.utils.quote(query)}"
        
        response = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        articles = []
        
        for result in soup.find_all(['article', 'div'], class_=['result', 'result__a', 'zd-result']):
            title_tag = result.find('a', class_='result__a') or result.find('h2') or result.find('a')
            snippet_tag = result.find('span', class_='result__snippet') or result.find('div', class_='snippet')
            
            if title_tag:
                title = title_tag.get_text().strip()[:80]
                snippet = snippet_tag.get_text().strip()[:150] if snippet_tag else ''
                url_val = title_tag.get('href', '')
                
                # Check if relevant
                if city.lower() in title.lower() or city.lower() in snippet.lower():
                    articles.append({
                        'title': title,
                        'snippet': snippet,
                        'url': url_val
                    })
        
        return articles[:3], "Searched"
    
    except Exception as e:
        logging.error(f"News search error: {e}")
        return [], f"Error: {e}"


def calculate_confidence(website_bio, news_mentions, linkedin_url):
    """Calculate confidence score"""
    score = 0.0
    
    if website_bio and len(website_bio) > 50:
        score += 0.4
    elif website_bio and len(website_bio) > 20:
        score += 0.2
    
    if news_mentions:
        score += min(0.3, len(news_mentions) * 0.1)
    
    if linkedin_url:
        score += 0.2
    
    return min(score, 1.0)


def enrich_personnel_profile(personnel_id, name, title, foundation_name, 
                            website, city, linkedin_url):
    """Enrich a single personnel profile"""
    logging.info(f"Processing: {name} ({foundation_name})")
    
    # 1. Scrape website bio
    bio, website_status = scrape_website_bio(website, name)
    
    # 2. Search news (slower, rate limit)
    news, news_status = search_news(name, city)
    
    # 3. Calculate confidence
    confidence = calculate_confidence(bio, news, linkedin_url)
    
    # 4. Build data sources
    sources = []
    if bio:
        sources.append("website")
    if news:
        sources.append("news")
    if linkedin_url:
        sources.append("linkedin_url")
    
    return {
        'personnel_id': personnel_id,
        'bio_summary': bio,
        'career_history': None,
        'education': None,
        'news_mentions': '\n\n'.join([f"- {a['title']}: {a['snippet']}" for a in news]) if news else None,
        'location_verified': 0,
        'data_sources': ', '.join(sources) if sources else None,
        'last_updated': datetime.now().isoformat(),
        'confidence_score': confidence,
        'website_status': website_status,
        'linkedin_status': 'pending',
        'news_status': news_status
    }


def batch_enrich_all(conn, limit=None):
    """Enrich all personnel profiles with progress tracking"""
    cursor = conn.cursor()
    
    query = """
        SELECT p.id, p.name, p.title, f.name, f.website, f.city, p.linkedin_url
        FROM personnel_990 p
        LEFT JOIN foundations f ON p.foundation_id = f.id
        WHERE p.name IS NOT NULL
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    total = len(rows)
    logging.info(f"Batch enrichment: {total} personnel")
    
    enriched = 0
    for i, row in enumerate(rows):
        personnel_id, name, title, f_name, website, city, linkedin = row
        
        print(f"\n[{i+1}/{total}] {name} - {f_name}")
        
        try:
            profile_data = enrich_personnel_profile(
                personnel_id=personnel_id,
                name=name,
                title=title,
                foundation_name=f_name,
                website=website,
                city=city,
                linkedin_url=linkedin
            )
            
            cursor.execute("""
                INSERT OR REPLACE INTO personnel_profiles (
                    personnel_id, bio_summary, career_history, education,
                    news_mentions, location_verified, data_sources, last_updated,
                    confidence_score, website_status, linkedin_status, news_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile_data['personnel_id'], profile_data['bio_summary'],
                profile_data['career_history'], profile_data['education'],
                profile_data['news_mentions'], profile_data['location_verified'],
                profile_data['data_sources'], profile_data['last_updated'],
                profile_data['confidence_score'], profile_data['website_status'],
                profile_data['linkedin_status'], profile_data['news_status']
            ))
            
            enriched += 1
            conn.commit()  # Commit after each record
            
            print(f"  Bio: {'Yes' if profile_data['bio_summary'] else 'No'}")
            print(f"  News: {len(profile_data['news_mentions'].split(chr(10))) if profile_data['news_mentions'] else 0}")
            print(f"  Confidence: {profile_data['confidence_score']:.1f}")
            
        except Exception as e:
            logging.error(f"Error enriching {name}: {e}")
            print(f"  ERROR: {e}")
    
    logging.info(f"Batch complete: {enriched}/{total} profiles enriched")
    return enriched, total


if __name__ == "__main__":
    conn = sqlite3.connect('database/louisiana_foundations.db')
    
    print("Starting bio enrichment...")
    enriched, total = batch_enrich_all(conn, limit=None)
    
    print(f"\n\nResults: {enriched}/{total} profiles enriched")
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            ROUND(AVG(confidence_score), 2) as avg_confidence,
            SUM(CASE WHEN bio_summary IS NOT NULL THEN 1 ELSE 0 END) as with_bio,
            SUM(CASE WHEN news_mentions IS NOT NULL THEN 1 ELSE 0 END) as with_news,
            COUNT(*) as total
        FROM personnel_profiles
    """)
    row = cursor.fetchone()
    
    print(f"\nSummary:")
    print(f"  Average confidence: {row[0]}")
    print(f"  With bio: {row[1]}")
    print(f"  With news: {row[2]}")
    print(f"  Total profiles: {row[3]}")
    
    conn.close()
