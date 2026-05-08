#!/usr/bin/env python3
"""
Extract email addresses from foundation websites and update CRM database.
"""

import sqlite3
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import time

# Email regex pattern
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

def extract_emails_from_url(url):
    """Extract email addresses from a website."""
    try:
        # Add https if not present
        if not url.startswith('http'):
            url = 'https://' + url
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return []
        
        # Extract emails from page content
        emails = EMAIL_PATTERN.findall(response.text)
        
        # Also extract from href links (sometimes emails are in links)
        soup = BeautifulSoup(response.text, 'html.parser')
        for link in soup.find_all('a', href=re.compile(r'mailto:')):
            email = link['href'].replace('mailto:', '')
            if email and email not in emails:
                emails.append(email)
        
        # Deduplicate and clean
        emails = list(set(emails))
        
        # Filter to emails that match the domain
        domain = urlparse(url).netloc
        if domain:
            domain_emails = [e for e in emails if domain.replace('www.', '') in e]
            if domain_emails:
                return domain_emails[:5]  # Return up to 5 domain-matched emails
        
        return emails[:5]  # Return up to 5 emails
        
    except Exception as e:
        print(f"  Error: {e}")
        return []

def main():
    conn = sqlite3.connect('database/louisiana_foundations.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get foundations with websites but no email
    cur.execute('''
        SELECT id, name, website 
        FROM foundations 
        WHERE website IS NOT NULL AND website != ''
        AND (email IS NULL OR email = '')
    ''')
    
    foundations = cur.fetchall()
    print(f"Found {len(foundations)} foundations needing email extraction\n")
    
    extracted_count = 0
    updated_count = 0
    
    for foundation in foundations:
        fid = foundation['id']
        fname = foundation['name']
        furl = foundation['website']
        
        print(f"Extracting emails from {fname}...")
        emails = extract_emails_from_url(furl)
        
        if emails:
            # Use the first email found
            email = emails[0]
            cur.execute('UPDATE foundations SET email = ? WHERE id = ?', (email, fid))
            conn.commit()
            print(f"  ✓ Found: {email}")
            extracted_count += 1
            updated_count += 1
        else:
            print(f"  ✗ No emails found")
        
        time.sleep(0.5)  # Be polite to servers
    
    print(f"\n=== Summary ===")
    print(f"Foundations processed: {len(foundations)}")
    print(f"Emails extracted: {extracted_count}")
    print(f"Records updated: {updated_count}")
    
    # Show results
    print("\n=== Updated Emails ===")
    cur.execute('''
        SELECT name, email FROM foundations 
        WHERE email IS NOT NULL AND email != ''
        ORDER BY name
    ''')
    for row in cur.fetchall():
        print(f"{row['name']}: {row['email']}")
    
    conn.close()

if __name__ == '__main__':
    main()
