import sqlite3

conn = sqlite3.connect('database/louisiana_foundations.db')
cur = conn.cursor()

# Check all bios for mismatches
cur.execute('SELECT id, name, bio FROM personnel_990 WHERE bio IS NOT NULL AND bio != ""')

mismatches = []
valid = 0

for id_, name, bio in cur.fetchall():
    name_lower = name.lower()
    bio_lower = bio.lower()
    
    # Get name parts, remove common prefixes/suffixes
    exclude = ['dr.', 'mr.', 'mrs.', 'ms.', 'phd', 'md', 'jr.', 'sr.', 'iii', 'iv', 'hon.', 'esq.']
    name_parts = [p for p in name.split() if p.lower() not in exclude]
    
    first_name = name_parts[0].lower() if name_parts else ''
    last_name = name_parts[-1].lower() if len(name_parts) > 1 else ''
    
    # Check if name appears in bio
    name_found = (first_name in bio_lower or last_name in bio_lower)
    
    # Check for organization names (not people)
    is_org = any(term in name_lower for term in ['center', 'foundation', 'cancer', 'hospital', 'clinic'])
    
    # Check for artifacts (text fragments)
    is_artifact = any(term in name.upper() for term in [
        'AT LARGE', 'GENERAL', 'REGIONAL', 'RESILIENCY',
        'RETIRED PEDIATRICIAN', 'GET O', 'PAST CHAIR', 'PAST CHAIRMAN', 'EX-OFFICIO'
    ])
    
    if not name_found or is_org or is_artifact:
        mismatches.append((id_, name, bio[:50]))
    else:
        valid += 1

print(f'Valid bios: {valid}')
print(f'Mismatches: {len(mismatches)}')

if mismatches:
    print('\nMismatched bios to clear:')
    for id_, name, bio_preview in mismatches:
        print(f'  {id_}: {name} - "{bio_preview}..."')
    
    # Clear mismatched bios
    if mismatches:
        ids = [m[0] for m in mismatches]
        placeholders = ','.join(['?'] * len(ids))
        cur.execute(f'UPDATE personnel_990 SET bio = NULL WHERE id IN ({placeholders})', ids)
        conn.commit()
        print(f'\nCleared {len(mismatches)} mismatched bios')

conn.close()
