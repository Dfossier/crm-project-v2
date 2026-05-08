#!/usr/bin/env python3
"""
Update database with extracted bios from subagent extraction.
"""

import sqlite3
import json
import re
from fuzzywuzzy import fuzz

# Foundation ID mapping
FOUNDATION_IDS = {
    "LSU Health Sciences Foundation": 26,
    "Baton Rouge Area Foundation": 9,
    "Community Foundation of North Louisiana": 19,
    "Business and Research Foundation": 20,  # BRF
    "International Dominican Foundation": 21,
    "LSU Foundation": 4,
    "Southwest Louisiana Charter Academy Foundation": 25,
}


def normalize_name(name):
    """Normalize name for fuzzy matching."""
    name = name.upper()
    name = name.replace('MD', '').replace('DR', '').replace('PHD', '')
    name = name.replace(' CPA', '').replace(' MPT', '')
    name = name.replace(' PHD', '').replace(' MD', '').replace(' DR', '')
    name = re.sub(r',\s*Jr\.', '', name, flags=re.I)
    name = re.sub(r',\s*Esq\.', '', name, flags=re.I)
    name = re.sub(r'Very\s+Rev\.', '', name, flags=re.I)
    name = re.sub(r'Rev\.', '', name, flags=re.I)
    name = re.sub(r'Mr\.', '', name, flags=re.I)
    name = re.sub(r'Ms\.', '', name, flags=re.I)
    name = re.sub(r'Mrs\.', '', name, flags=re.I)
    name = re.sub(r'Sr\.', '', name, flags=re.I)
    name = re.sub(r'Fr\.', '', name, flags=re.I)
    name = re.sub(r'O\.P\.', '', name, flags=re.I)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def main():
    # Load extracted bios
    with open('/home/dfoss/crm/extracted_bios_subagent.json', 'r') as f:
        extracted = json.load(f)
    
    # Connect to database
    conn = sqlite3.connect('/home/dfoss/crm/database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    # Get board members
    cursor.execute("""
        SELECT id, name, foundation_id 
        FROM personnel_990 
        WHERE is_board_member = 1
    """)
    board_members = cursor.fetchall()
    
    print("=" * 70)
    print("UPDATING BIOS FROM EXTRACTED DATA")
    print("=" * 70)
    
    updated_count = 0
    matched = []
    
    for pid, pname, pfid in board_members:
        db_name_norm = normalize_name(pname)
        
        # Find matching foundation
        for foundation_name, foundation_bios in extracted.items():
            foundation_id = FOUNDATION_IDS.get(foundation_name)
            
            if foundation_id == pfid:
                bios = foundation_bios.get('bios', {})
                
                for bio_name, bio in bios.items():
                    bio_name_norm = normalize_name(bio_name)
                    similarity = fuzz.ratio(db_name_norm, bio_name_norm)
                    
                    # Accept match if similarity >= 80 and bio is useful
                    if similarity >= 80 and bio and len(bio.strip()) > 5:
                        cursor.execute("""
                            UPDATE personnel_990 
                            SET bio = ? 
                            WHERE id = ?
                        """, (bio, pid))
                        updated_count += 1
                        matched.append({
                            'personnel_id': pid,
                            'name': pname,
                            'bio': bio,
                            'similarity': similarity,
                            'extracted_name': bio_name
                        })
                        break
    
    conn.commit()
    
    # Show matches
    matched.sort(key=lambda x: x['similarity'], reverse=True)
    
    print(f"\nMatched {len(matched)} board members:\n")
    
    for m in matched[:30]:
        print(f"  ✓ {m['name'][:35]:<35} (match: {m['similarity']:3.0f}%)")
        print(f"      Bio: {m['bio'][:70]}...")
    
    if len(matched) > 30:
        print(f"\n  ... and {len(matched) - 30} more matches")
    
    conn.close()
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total board members: {len(board_members)}")
    print(f"Bios updated: {updated_count}")
    print(f"Match rate: {100*updated_count/len(board_members):.1f}%")
    
    # Final stats
    conn = sqlite3.connect('/home/dfoss/crm/database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1 AND bio IS NOT NULL AND bio != ''")
    with_bios = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1")
    total_board = cursor.fetchone()[0]
    
    print(f"\nBoard members with bios: {with_bios}/{total_board} ({100*with_bios/total_board:.1f}%)")
    
    conn.close()


if __name__ == '__main__':
    main()
