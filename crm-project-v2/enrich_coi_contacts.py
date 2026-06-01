#!/usr/bin/env python3
"""
Enrich centers_of_influence records with contact info from LinkedIn profiles.
Extracts: phone, email, company address, city, state
"""

import sqlite3
import requests
import re
from bs4 import BeautifulSoup
import time
import json

# LinkedIn profile patterns
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_PATTERN = re.compile(r'\+?\d{10,}')

def extract_contact_info_from_linkedin(linkedin_url):
    """Extract contact info from LinkedIn profile page."""
    try:
        if not linkedin_url or not linkedin_url.startswith('http'):
            return {}
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        response = requests.get(linkedin_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        info = {}
        
        # Try to find contact info sections
        # LinkedIn often has contact info in specific classes
        
        # Search for email patterns in the page
        emails = EMAIL_PATTERN.findall(response.text)
        # Filter to likely professional emails
        professional_emails = [e for e in emails if '@' in e and len(e) > 5]
        if professional_emails:
            info['email'] = professional_emails[0]
        
        # Search for phone patterns
        phones = PHONE_PATTERN.findall(response.text)
        if phones:
            info['phone'] = phones[0]
        
        # Try to find company info from About section or Experience
        # LinkedIn stores this in data attributes
        for element in soup.find_all(['div', 'section'], recursive=True):
            if element.get('data-test', '') in ['PMPH_COMPANY', 'PMPH_LOCATION']:
                if element.get_text(strip=True):
                    if 'company' in element.get('data-test', '').lower():
                        info['company'] = element.get_text(strip=True)
                    elif 'location' in element.get('data-test', '').lower():
                        info['location'] = element.get_text(strip=True)
        
        # Try JSON-LD structured data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if 'contactPoint' in data:
                        cp = data['contactPoint']
                        if isinstance(cp, dict):
                            info['phone'] = cp.get('telephone')
                            info['email'] = cp.get('email')
                    if 'address' in data:
                        addr = data['address']
                        if isinstance(addr, dict):
                            info['address'] = addr.get('streetAddress')
                            info['city'] = addr.get('addressLocality')
                            info['state'] = addr.get('addressRegion')
            except:
                pass
        
        return info
        
    except Exception as e:
        print(f"  Error processing {linkedin_url}: {e}")
        return {}

def main():
    conn = sqlite3.connect('database/louisiana_foundations.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get COI records with LinkedIn URLs but missing contact info
    cur.execute('''
        SELECT id, name, linkedin_url, employer
        FROM centers_of_influence
        WHERE linkedin_url IS NOT NULL 
          AND linkedin_url != ''
          AND (phone IS NULL OR phone = '')
        LIMIT 50
    ''')
    
    cois = cur.fetchall()
    print(f"Processing {len(cois)} centers of influence...\n")
    
    updated = 0
    for coi in cois:
        print(f"Processing {coi['name']}...")
        info = extract_contact_info_from_linkedin(coi['linkedin_url'])
        
        if info:
            updates = []
            params = []
            
            if 'email' in info:
                updates.append('email = ?')
                params.append(info['email'])
            
            if 'phone' in info:
                updates.append('phone = ?')
                params.append(info['phone'])
            
            if 'address' in info:
                updates.append('employer_address = ?')
                params.append(info['address'])
            
            if 'city' in info:
                updates.append('employer_city = ?')
                params.append(info['city'])
            
            if 'state' in info:
                updates.append('employer_state = ?')
                params.append(info['state'])
            
            if updates:
                params.append(coi['id'])
                cur.execute(f'''
                    UPDATE centers_of_influence 
                    SET {', '.join(updates)}
                    WHERE id = ?
                ''', params)
                conn.commit()
                print(f"  Updated: {info}")
                updated += 1
            else:
                print(f"  No contact info found")
        else:
            print(f"  No data returned")
        
        time.sleep(0.5)  # Be polite
    
    print(f"\n=== Summary ===")
    print(f"Processed: {len(cois)}")
    print(f"Updated: {updated}")
    
    # Show stats
    cur.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(email) as has_email,
            COUNT(phone) as has_phone,
            COUNT(employer_address) as has_address
        FROM centers_of_influence
    ''')
    stats = cur.fetchone()
    print(f"\n=== Overall Stats ===")
    print(f"Total COIs: {stats['total']}")
    print(f"With email: {stats['has_email']}")
    print(f"With phone: {stats['has_phone']}")
    print(f"With address: {stats['has_address']}")
    
    conn.close()

if __name__ == '__main__':
    main()
