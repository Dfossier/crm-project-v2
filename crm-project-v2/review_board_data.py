#!/usr/bin/env python3
"""
Quick review of board member data for CRM.
Shows current state, gaps, and recommendations.
"""

import sqlite3
import json

def main():
    conn = sqlite3.connect('database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    print("=" * 70)
    print("BOARD MEMBER DATA REVIEW")
    print("=" * 70)
    
    # Overall stats
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1")
    total_board = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1 AND bio IS NOT NULL AND bio != ''")
    with_bios = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM personnel_990 WHERE is_board_member = 1 AND bio IS NULL OR bio = ''")
    without_bios = cursor.fetchone()[0]
    
    print(f"\n📊 OVERALL STATS")
    print(f"   Total board members: {total_board}")
    print(f"   With bios: {with_bios} ({100*with_bios/total_board:.1f}%)")
    print(f"   Without bios: {without_bios} ({100*without_bios/total_board:.1f}%)")
    
    # By foundation
    print(f"\n📊 BY FOUNDATION")
    cursor.execute("""
        SELECT f.name, 
               SUM(CASE WHEN p.is_board_member = 1 THEN 1 ELSE 0 END) as board_count,
               SUM(CASE WHEN p.is_board_member = 1 AND p.bio IS NOT NULL AND p.bio != '' THEN 1 ELSE 0 END) as with_bio
        FROM personnel_990 p
        JOIN foundations f ON p.foundation_id = f.id
        GROUP BY f.id, f.name
        ORDER BY board_count DESC
    """)
    
    for row in cursor.fetchall():
        foundation, board_count, with_bio = row
        if board_count > 0:
            pct = 100 * with_bio / board_count
            print(f"   {foundation}: {board_count} members, {with_bio} bios ({pct:.0f}%)")
    
    # Sample with bios
    print(f"\n✅ SAMPLE: Board Members WITH Bios")
    cursor.execute("""
        SELECT p.name, f.name as foundation, p.bio
        FROM personnel_990 p
        JOIN foundations f ON p.foundation_id = f.id
        WHERE p.is_board_member = 1 AND p.bio IS NOT NULL AND p.bio != ''
        ORDER BY f.name, p.name
        LIMIT 10
    """)
    
    for row in cursor.fetchall():
        name, foundation, bio = row
        print(f"   [{foundation}] {name}")
        print(f"      Bio: {bio[:100]}...")
        print()
    
    # Sample without bios
    print(f"\n❌ SAMPLE: Board Members WITHOUT Bios")
    cursor.execute("""
        SELECT p.name, f.name as foundation
        FROM personnel_990 p
        JOIN foundations f ON p.foundation_id = f.id
        WHERE p.is_board_member = 1 AND (p.bio IS NULL OR p.bio = '')
        ORDER BY f.name, p.name
        LIMIT 10
    """)
    
    for row in cursor.fetchall():
        name, foundation = row
        print(f"   [{foundation}] {name}")
    
    # Check extracted bios file
    print(f"\n📁 EXTRACTED BIOS FILE")
    try:
        with open('extracted_bios.json', 'r') as f:
            bios = json.load(f)
        for foundation, fbios in bios.items():
            if fbios:
                print(f"   {foundation}: {len(fbios)} bios extracted")
                for name, bio in list(fbios.items())[:2]:
                    print(f"      - {name}: {bio[:60]}...")
            else:
                print(f"   {foundation}: 0 bios (name+title only format)")
    except FileNotFoundError:
        print("   No extracted_bios.json found")
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS")
    print(f"   1. Extract professional titles from board pages (100% coverage)")
    print(f"   2. Search 'About Us' / 'Leadership' pages for detailed bios")
    print(f"   3. Manual entry for key personnel (board chairs, presidents)")
    print(f"   4. LinkedIn search for remaining ~100 board members")
    
    # Gap analysis
    print(f"\n🎯 PRIORITY TARGETS")
    cursor.execute("""
        SELECT f.name as foundation, 
               SUM(CASE WHEN p.is_board_member = 1 AND (p.board_role LIKE '%Chair%' OR p.board_role LIKE '%President%' OR p.board_role LIKE '%CEO%') THEN 1 ELSE 0 END) as key_roles
        FROM personnel_990 p
        JOIN foundations f ON p.foundation_id = f.id
        WHERE p.is_board_member = 1
        GROUP BY f.id, f.name
        HAVING key_roles > 0
    """)
    
    print("   Key roles (Chair/President/CEO) without bios:")
    for row in cursor.fetchall():
        foundation, count = row
        cursor.execute("""
            SELECT p.name, p.board_role
            FROM personnel_990 p
            JOIN foundations f ON p.foundation_id = f.id
            WHERE p.is_board_member = 1 
              AND f.id = ?
              AND (p.board_role LIKE '%Chair%' OR p.board_role LIKE '%President%' OR p.board_role LIKE '%CEO%')
              AND (p.bio IS NULL OR p.bio = '')
        """, (foundation,))
        
        for pname, prole in cursor.fetchall():
            print(f"      [{foundation}] {pname} ({prole})")
    
    conn.close()
    print(f"\n{'=' * 70}")

if __name__ == '__main__':
    main()
