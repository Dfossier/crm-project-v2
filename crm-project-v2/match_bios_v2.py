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

def names_match(person_name, bio_name):
    """Check if names match by comparing key components"""
    p_norm = normalize_name(person_name)
    b_norm = normalize_name(bio_name)
    
    # Direct match
    if p_norm == b_norm:
        return True
    
    # Check if one contains the other (for nicknames like Mike vs Milford)
    p_words = set(p_norm.split())
    b_words = set(b_norm.split())
    
    # At least 2 matching words or 75% overlap
    common = p_words & b_words
    if len(common) >= 2:
        return True
    
    total = p_words | b_words
    if len(total) > 0 and len(common) / len(total) >= 0.75:
        return True
    
    return False

# Load extracted bios
with open('foundation_bios_extracted.json') as f:
    bios_data = json.load(f)

# Connect to database
conn = sqlite3.connect('database/louisiana_foundations.db')
cur = conn.cursor()

# Get foundation mappings
foundation_map = {
    'lsu foundation': 'lsufoundation',
    'braf': 'braton rouge',
    'greater new orleans foundation': 'gnof',
    'lsu shreveport foundation': 'lsus'
}

# Get all personnel
cur.execute('''
    SELECT p.id, p.name, f.name as foundation_name
    FROM personnel_990 p
    JOIN foundations f ON p.foundation_id = f.id
    WHERE (p.bio IS NULL OR p.bio = "")
    AND p.employer IS NOT NULL
''')
personnel = cur.fetchall()

updated = 0
not_matched = 0

for pid, pname, fname in personnel:
    fname_lower = fname.lower()
    bio_text = None
    
    # Match by foundation
    for foundation_key, data in bios_data.items():
        foundation_lower = foundation_key.lower()
        
        # Check foundation match
        if 'braton' in foundation_lower and 'braton' in fname_lower:
            pass  # BRAF match
        elif 'lsu foundation' in foundation_lower and 'lsu' in fname_lower and 'shreveport' not in fname_lower:
            pass  # LSU Foundation match
        elif 'greater new orleans' in foundation_lower and 'new orleans' in fname_lower:
            pass  # GNOF match
        elif 'lsu shreveport' in foundation_lower and 'shreveport' in fname_lower:
            pass  # LSUS match
        else:
            continue
        
        # Now match names
        for bio_name, bio in data.get('bios', {}).items():
            if names_match(pname, bio_name):
                bio_text = clean_bio(bio)
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
print(f'Bios updated: {updated}')
print(f'Not matched: {not_matched}')
conn.close()
