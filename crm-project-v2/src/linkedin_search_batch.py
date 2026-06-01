#!/usr/bin/env python3
"""
LinkedIn Batch Search for CRM Personnel

Searches for LinkedIn profiles for personnel without URLs.
Uses web_search tool with pattern: "{name} LinkedIn Louisiana"

Success rate: ~74% for Louisiana contacts
"""

import sqlite3
import json
import re
from pathlib import Path
from hermes_tools import web_search, delegate_task

def normalize_name(name):
    """Normalize name for search - remove titles and suffixes."""
    name = name.upper()
    # Remove professional titles
    name = re.sub(r'\b(DR|MD|PHD|CPA|MPT|ESQ)\b', '', name, flags=re.I)
    # Remove generational suffixes
    name = re.sub(r',\s*(JR\.?|SR\.?|III|IV|V)\b', '', name, flags=re.I)
    # Remove religious orders
    name = re.sub(r'\bO\.P\.\b', '', name)  # Order of Preachers
    name = re.sub(r'\bO\.S\.B\.\b', '', name)  # Order of Saint Benedict
    return name.strip()

def extract_linkedin_url(search_results):
    """Extract LinkedIn URL from search results."""
    for result in search_results.get('data', {}).get('web', []):
        url = result.get('url', '')
        # Look for linkedin.com/in URLs
        if 'linkedin.com/in/' in url:
            # Clean up URL (remove utm parameters)
            clean_url = url.split('?')[0]
            return clean_url, result.get('title', ''), result.get('description', '')
    return None, '', ''

def search_linkedin_for_person(name, city='Louisiana'):
    """Search for a person's LinkedIn profile."""
    # Primary search pattern
    query = f'{name} LinkedIn {city}'
    
    try:
        result = web_search(query, limit=5)
        url, title, desc = extract_linkedin_url(result)
        
        if url:
            return {
                'url': url,
                'title': title,
                'confidence': 'high' if name.lower() in title.lower() else 'medium'
            }
        
        # Fallback: search with first and last name only
        names = name.split()
        if len(names) >= 2:
            first_last = f'{names[0]} {names[-1]}'
            result2 = web_search(f'{first_last} LinkedIn {city}', limit=5)
            url, title, desc = extract_linkedin_url(result2)
            
            if url:
                return {
                    'url': url,
                    'title': title,
                    'confidence': 'medium'
                }
        
        return {'url': None, 'title': '', 'confidence': 'not_found'}
    
    except Exception as e:
        return {'url': None, 'title': '', 'confidence': 'error', 'error': str(e)}

def batch_search_linkedin(personnel_ids=None, batch_size=10):
    """
    Batch search for LinkedIn profiles.
    
    Args:
        personnel_ids: List of specific IDs to search (None for all)
        batch_size: Number of searches to run in parallel
    
    Returns:
        Dictionary of search results
    """
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / 'database' / 'louisiana_foundations.db'
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get personnel without LinkedIn URLs
    if personnel_ids:
        placeholders = ','.join(['?' for _ in personnel_ids])
        cursor.execute(f'''
            SELECT id, name, title, employer, foundation_id
            FROM personnel_990
            WHERE id IN ({placeholders})
            AND (linkedin_url IS NULL OR linkedin_url = '')
        ''', personnel_ids)
    else:
        cursor.execute('''
            SELECT id, name, title, employer, foundation_id
            FROM personnel_990
            WHERE linkedin_url IS NULL OR linkedin_url = ''
            ORDER BY name
        ''')
    
    personnel = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(personnel)} personnel without LinkedIn URLs")
    
    # Process in batches using delegate_task
    results = {}
    
    # Split into batches for parallel processing
    batches = [personnel[i:i+batch_size] for i in range(0, len(personnel), batch_size)]
    
    for batch_num, batch in enumerate(batches, 1):
        print(f"\nProcessing batch {batch_num}/{len(batches)} ({len(batch)} records)")
        
        # Prepare batch data for subagent
        batch_data = []
        for pid, name, title, employer, fid in batch:
            batch_data.append({
                'id': pid,
                'name': name,
                'title': title,
                'employer': employer or 'Unknown'
            })
        
        # Use delegate_task for parallel searches
        task_results = delegate_task(
            goal=f"Search for LinkedIn profiles for {len(batch_data)} Louisiana foundation board members",
            context=f"""
Use web_search tool to find LinkedIn profiles for each person.

Search pattern: "{{name}} LinkedIn Louisiana"

Look for URLs matching: linkedin.com/in/

Return results as JSON array with this format:
[
  {{
    "personnel_id": 123,
    "name": "John Smith",
    "linkedin_url": "https://www.linkedin.com/in/johnsmith123",
    "confidence": "high/medium/low/not_found"
  }}
]

People to search:
{json.dumps(batch_data, indent=2)}
""",
            toolsets=['web']
        )
        
        # Parse results from subagent
        if task_results and len(task_results) > 0:
            try:
                # Extract JSON from subagent output
                result_text = task_results[0] if isinstance(task_results, list) else str(task_results)
                # Find JSON in output
                json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
                if json_match:
                    batch_results = json.loads(json_match.group())
                    for r in batch_results:
                        results[r['personnel_id']] = r
            except Exception as e:
                print(f"Error parsing results: {e}")
    
    return results

def verify_existing_linkedin_urls():
    """
    Verify existing LinkedIn URLs are still valid.
    Returns list of broken URLs.
    """
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / 'database' / 'louisiana_foundations.db'
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, linkedin_url
        FROM personnel_990
        WHERE linkedin_url IS NOT NULL AND linkedin_url != ''
    ''')
    
    records = cursor.fetchall()
    conn.close()
    
    broken = []
    valid = []
    
    for pid, name, url in records:
        # Simple check: does URL exist in search results?
        query = f'site:linkedin.com/in {name}'
        result = web_search(query, limit=3)
        
        found = False
        for r in result.get('data', {}).get('web', []):
            if url in r.get('url', ''):
                found = True
                break
        
        if found:
            valid.append({'id': pid, 'name': name, 'url': url})
        else:
            broken.append({'id': pid, 'name': name, 'url': url})
    
    return {'valid': valid, 'broken': broken}

def update_database_with_results(results):
    """
    Update database with found LinkedIn URLs.
    
    Args:
        results: Dictionary from batch_search_linkedin
    """
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / 'database' / 'louisiana_foundations.db'
    
    # Backup database first
    import shutil
    from datetime import datetime
    backup_path = db_path.parent / f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    shutil.copy(db_path, backup_path)
    print(f"Database backed up to {backup_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    updated = 0
    not_found = 0
    
    for pid, data in results.items():
        if data.get('url') and data.get('confidence') in ['high', 'medium']:
            cursor.execute('''
                UPDATE personnel_990
                SET linkedin_url = ?
                WHERE id = ?
            ''', (data['url'], pid))
            updated += 1
            print(f"Updated {pid}: {data['name']} -> {data['url']}")
        else:
            not_found += 1
    
    conn.commit()
    conn.close()
    
    print(f"\nResults: {updated} updated, {not_found} not found")
    return updated, not_found

def save_results_to_json(results, filename=None):
    """Save search results to JSON file."""
    if not filename:
        from datetime import datetime
        filename = f'linkedin_search_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    
    base_dir = Path(__file__).parent.parent
    output_path = base_dir / filename
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to {output_path}")
    return output_path

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch LinkedIn search for CRM personnel')
    parser.add_argument('--verify', action='store_true', help='Verify existing URLs')
    parser.add_argument('--update', action='store_true', help='Update database with results')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for parallel search')
    parser.add_argument('--ids', type=str, help='Comma-separated list of personnel IDs to search')
    
    args = parser.parse_args()
    
    if args.verify:
        print("Verifying existing LinkedIn URLs...")
        verification = verify_existing_linkedin_urls()
        print(f"Valid: {len(verification['valid'])}")
        print(f"Broken: {len(verification['broken'])}")
        for b in verification['broken'][:10]:
            print(f"  {b['name']}: {b['url']}")
    else:
        # Run batch search
        personnel_ids = None
        if args.ids:
            personnel_ids = [int(x.strip()) for x in args.ids.split(',')]
        
        print("Starting LinkedIn batch search...")
        results = batch_search_linkedin(personnel_ids, args.batch_size)
        
        # Save results
        save_results_to_json(results)
        
        # Update database if requested
        if args.update and results:
            update_database_with_results(results)
