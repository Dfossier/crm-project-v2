import sqlite3
import json
import re

def normalize_name(name):
    """Remove titles, suffixes, normalize whitespace"""
    name = name.upper()
    name = re.sub(r'\b(DR|MD|PHD|CPA|MPT|ESQ|HON|THE HONORABLE)\b', '', name, flags=re.I)
    name = re.sub(r',?\s*(JR|SR|III|IV|II)\.?', '', name, flags=re.I)
    name = name.replace('"', '').replace('"', '').replace('"', '')
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def clean_bio(bio):
    """Clean extracted bio text"""
    bio = re.sub(r'\*([^*]+)\*', r'\1', bio)
    bio = re.sub(r'\n#+\s*', '\n', bio)
    bio = re.sub(r'\n\s*\n', '\n', bio)
    bio = re.sub(r'\s+', ' ', bio)
    return bio.strip()

def name_matches(person_name, bio_name):
    """Calculate name similarity"""
    p_norm = normalize_name(person_name)
    b_norm = normalize_name(bio_name)
    
    common = set(p_norm.split()) & set(b_norm.split())
    total = set(p_norm.split()) | set(b_norm.split())
    
    if not total:
        return 0
    return int(100 * len(common) / len(total))

# Load extracted bios
with open('foundation_bios_extracted.json') as f:
    bios_data = json.load(f)

# Connect to database
conn = sqlite3.connect('database/louisiana_foundations.db')
cur = conn.cursor()

# Get all personnel with foundation context
cur.execute('''
    SELECT p.id, p.name, p.foundation_id, f.name as foundation_name
    FROM personnel_990 p
    JOIN foundations f ON p.foundation_id = f.id
    WHERE p.bio IS NULL OR p.bio = ""
''')
personnel = cur.fetchall()

updated = 0
matched = 0
not_matched = 0

for pid, pname, foid, fname in personnel:
    bio_text = None
    for foundation, data in bios_data.items():
        if foundation.upper() not in fname.upper() and fname.upper() not in foundation.upper():
            continue
            
        for bio_name, bio in data.get('bios', {}).items():
            similarity = name_matches(pname, bio_name)
            if similarity >= 75:
                pname_lower = pname.lower()
                bio_lower = bio.lower()
                name_parts = pname_lower.split()
                first_name = name_parts[0].lower()
                last_name = name_parts[-1].lower() if len(name_parts) > 1 else ''
                
                name_in_bio = (first_name in bio_lower or last_name in bio_lower)
                
                if name_in_bio:
                    bio_text = clean_bio(bio)
                    matched += 1
                    break
        
        if bio_text:
            break
    
    if bio_text:
        cur.execute('UPDATE personnel_990 SET bio = ? WHERE id = ?', (bio_text, pid))
        updated += 1
        print(f'Updated: {pname}')
    else:
        not_matched += 1

conn.commit()
print(f'\n=== Summary ===')
print(f'Total processed: {len(personnel)}')
print(f'Bios matched: {matched}')
print(f'Bios updated: {updated}')
print(f'Not matched: {not_matched}')
conn.close()
