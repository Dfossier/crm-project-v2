#!/usr/bin/env python3
"""
Demo script to populate database with sample Louisiana foundation data.
This shows what the real system would discover through data acquisition.
"""

import sqlite3
from pathlib import Path
from datetime import datetime

# Sample Louisiana foundations data based on publicly available information
SAMPLE_FOUNDATIONS = [
    {
        'ein': '72-0303994',
        'name': 'The Irene W. and C.B. Pennington Foundation',
        'legal_name': 'The Irene W. and C.B. Pennington Foundation',
        'city': 'Baton Rouge',
        'state': 'LA',
        'zip_code': '70809',
        'website': 'http://penningtonfoundation.org',
        'investment_assets': 131724635,
        'annual_grants': 6500000,
        'annual_revenue': 8200000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'private'
    },
    {
        'ein': '72-1234501',
        'name': 'Baton Rouge Area Foundation',
        'legal_name': 'Baton Rouge Area Foundation Inc.',
        'city': 'Baton Rouge',
        'state': 'LA',
        'zip_code': '70801',
        'website': 'http://brafoundation.org',
        'investment_assets': 85000000,
        'annual_grants': 4200000,
        'annual_revenue': 5800000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'community'
    },
    {
        'ein': '72-1234502',
        'name': 'Greater New Orleans Foundation',
        'legal_name': 'Greater New Orleans Foundation',
        'city': 'New Orleans',
        'state': 'LA',
        'zip_code': '70130',
        'website': 'http://gnof.org',
        'investment_assets': 125000000,
        'annual_grants': 8500000,
        'annual_revenue': 12000000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'community'
    },
    {
        'ein': '72-1234503',
        'name': 'The Brown Foundation Inc.',
        'legal_name': 'The Brown Foundation Inc. of Louisiana',
        'city': 'New Orleans',
        'state': 'LA',
        'zip_code': '70112',
        'investment_assets': 45000000,
        'annual_grants': 2100000,
        'annual_revenue': 2800000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'family'
    },
    {
        'ein': '72-1234504',
        'name': 'Louisiana Endowment for the Humanities',
        'legal_name': 'Louisiana Endowment for the Humanities',
        'city': 'New Orleans',
        'state': 'LA',
        'zip_code': '70130',
        'website': 'http://leh.org',
        'investment_assets': 15000000,
        'annual_grants': 850000,
        'annual_revenue': 1200000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'private'
    },
    {
        'ein': '72-1234505',
        'name': 'Entergy Corporation Foundation',
        'legal_name': 'Entergy Corporation Foundation',
        'city': 'New Orleans',
        'state': 'LA',
        'zip_code': '70161',
        'investment_assets': 25000000,
        'annual_grants': 1800000,
        'annual_revenue': 2200000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'corporate'
    },
    {
        'ein': '72-1234506',
        'name': 'The Azby Fund',
        'legal_name': 'The Azby Fund',
        'city': 'Shreveport',
        'state': 'LA',
        'zip_code': '71101',
        'investment_assets': 35000000,
        'annual_grants': 1500000,
        'annual_revenue': 2100000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'private'
    },
    {
        'ein': '72-1234507',
        'name': 'Community Foundation of Acadiana',
        'legal_name': 'Community Foundation of Acadiana',
        'city': 'Lafayette',
        'state': 'LA',
        'zip_code': '70506',
        'website': 'http://cfacadiana.org',
        'investment_assets': 28000000,
        'annual_grants': 1600000,
        'annual_revenue': 2000000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'community'
    },
    {
        'ein': '72-1234508',
        'name': 'The McIlhenny Company Foundation',
        'legal_name': 'The McIlhenny Company Foundation',
        'city': 'Avery Island',
        'state': 'LA',
        'zip_code': '70513',
        'investment_assets': 12000000,
        'annual_grants': 650000,
        'annual_revenue': 850000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'corporate'
    },
    {
        'ein': '72-1234509',
        'name': 'The Zemurray Foundation',
        'legal_name': 'The Zemurray Foundation',
        'city': 'New Orleans',
        'state': 'LA',
        'zip_code': '70115',
        'investment_assets': 65000000,
        'annual_grants': 3200000,
        'annual_revenue': 4100000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'family'
    }
]

# Sample personnel data
SAMPLE_PERSONNEL = [
    {
        'foundation_name': 'The Irene W. and C.B. Pennington Foundation',
        'personnel': [
            {'name': 'William C. Richardson', 'title': 'Chairman', 'compensation': 0},
            {'name': 'Dana Brown', 'title': 'President', 'compensation': 185000},
            {'name': 'John Smith', 'title': 'Executive Director', 'compensation': 145000}
        ]
    },
    {
        'foundation_name': 'Greater New Orleans Foundation',
        'personnel': [
            {'name': 'Andy Kopplin', 'title': 'President & CEO', 'compensation': 220000},
            {'name': 'Sarah Johnson', 'title': 'VP Programs', 'compensation': 125000},
            {'name': 'Michael Davis', 'title': 'CFO', 'compensation': 135000}
        ]
    }
]

# Sample focus areas
SAMPLE_FOCUS_AREAS = [
    {
        'foundation_name': 'The Irene W. and C.B. Pennington Foundation',
        'areas': [
            {'category': 'Education', 'subcategory': 'Higher Education', 'is_primary': True},
            {'category': 'Health', 'subcategory': 'Medical Research', 'is_primary': False},
            {'category': 'Arts', 'subcategory': 'Cultural Programs', 'is_primary': False}
        ]
    },
    {
        'foundation_name': 'Greater New Orleans Foundation',
        'areas': [
            {'category': 'Community Development', 'subcategory': 'Disaster Recovery', 'is_primary': True},
            {'category': 'Education', 'subcategory': 'K-12 Education', 'is_primary': True},
            {'category': 'Health', 'subcategory': 'Public Health', 'is_primary': False}
        ]
    }
]

def populate_demo_data():
    """Populate database with sample foundation data."""
    
    base_dir = Path(__file__).parent
    db_path = base_dir / "database" / "louisiana_foundations.db"
    schema_path = base_dir / "database" / "schema.sql"
    
    # Ensure directories exist
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("🏛️  Creating Louisiana Foundations Demo Database")
    print("=" * 60)
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if schema exists, create if needed
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='foundations';")
            if cursor.fetchone() is None:
                # Apply schema only if tables don't exist
                if schema_path.exists():
                    with open(schema_path, 'r') as f:
                        conn.executescript(f.read())
                    print("✅ Database schema applied")
            else:
                print("✅ Database schema already exists")
            
            # Clear existing demo data
            cursor.execute("DELETE FROM interactions")
            cursor.execute("DELETE FROM grants") 
            cursor.execute("DELETE FROM focus_areas")
            cursor.execute("DELETE FROM personnel")
            cursor.execute("DELETE FROM financial_history")
            cursor.execute("DELETE FROM foundations")
            
            # Insert foundations
            print("🏛️  Inserting foundation data...")
            foundation_ids = {}
            
            for foundation in SAMPLE_FOUNDATIONS:
                cursor.execute("""
                    INSERT INTO foundations 
                    (ein, name, legal_name, city, state, zip_code, website,
                     investment_assets, annual_grants, annual_revenue, filing_year,
                     tax_exempt_status, foundation_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    foundation['ein'], foundation['name'], foundation['legal_name'],
                    foundation['city'], foundation['state'], foundation['zip_code'],
                    foundation.get('website'), foundation['investment_assets'],
                    foundation['annual_grants'], foundation['annual_revenue'],
                    foundation['filing_year'], foundation['tax_exempt_status'],
                    foundation['foundation_type']
                ))
                
                foundation_ids[foundation['name']] = cursor.lastrowid
                print(f"   Added: {foundation['name']} (${foundation['investment_assets']/1e6:.1f}M)")
            
            # Insert personnel
            print("👥 Inserting personnel data...")
            for org in SAMPLE_PERSONNEL:
                foundation_id = foundation_ids[org['foundation_name']]
                for person in org['personnel']:
                    cursor.execute("""
                        INSERT INTO personnel 
                        (foundation_id, name, title, compensation, role, is_current)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        foundation_id, person['name'], person['title'],
                        person['compensation'], 'officer', True
                    ))
                print(f"   Added {len(org['personnel'])} personnel for {org['foundation_name']}")
            
            # Insert focus areas
            print("🎯 Inserting focus areas...")
            for org in SAMPLE_FOCUS_AREAS:
                foundation_id = foundation_ids[org['foundation_name']]
                for area in org['areas']:
                    cursor.execute("""
                        INSERT INTO focus_areas 
                        (foundation_id, category, subcategory, is_primary)
                        VALUES (?, ?, ?, ?)
                    """, (
                        foundation_id, area['category'], area['subcategory'], area['is_primary']
                    ))
                print(f"   Added {len(org['areas'])} focus areas for {org['foundation_name']}")
            
            # Add some sample interactions
            print("📞 Adding sample interactions...")
            cursor.execute("""
                INSERT INTO interactions 
                (foundation_id, interaction_type, contact_person, subject, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (
                foundation_ids['The Irene W. and C.B. Pennington Foundation'],
                'research', 'Research Team', 'Initial prospect research',
                'Large education-focused foundation. Strong interest in higher education and medical research. Board includes prominent business leaders.'
            ))
            
            cursor.execute("""
                INSERT INTO interactions 
                (foundation_id, interaction_type, contact_person, subject, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (
                foundation_ids['Greater New Orleans Foundation'],
                'email', 'Andy Kopplin', 'Introduction and capability overview',
                'Sent introduction email to President & CEO. Foundation focused on community development and disaster recovery. Good potential partner for regional initiatives.'
            ))
            
            conn.commit()
            
            # Display summary
            print("\n📊 Demo Database Summary:")
            cursor.execute("SELECT COUNT(*) FROM foundations")
            foundation_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(investment_assets) FROM foundations")
            total_assets = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(annual_grants) FROM foundations")
            total_grants = cursor.fetchone()[0]
            
            print(f"   Foundations: {foundation_count}")
            print(f"   Total Assets: ${total_assets/1e6:.0f}M")
            print(f"   Annual Grants: ${total_grants/1e6:.0f}M")
            print(f"   Average Payout: {(total_grants/total_assets)*100:.1f}%")
            
            # Top foundations by assets
            print("\n🏆 Top Foundations by Assets:")
            cursor.execute("""
                SELECT name, city, investment_assets, annual_grants
                FROM foundations 
                ORDER BY investment_assets DESC 
                LIMIT 5
            """)
            
            for i, row in enumerate(cursor.fetchall(), 1):
                name, city, assets, grants = row
                print(f"   {i}. {name}")
                print(f"      📍 {city} | 💰 ${assets/1e6:.0f}M assets | 🎁 ${grants/1e6:.1f}M grants")
            
            print("\n✅ Demo database created successfully!")
            print(f"   Database location: {db_path}")
            print("\n🚀 Next steps:")
            print("1. Activate virtual environment: source venv/bin/activate")
            print("2. Install requirements: pip install -r requirements.txt") 
            print("3. Start CRM interface: python3 run.py webapp")
            
            return True
            
    except Exception as e:
        print(f"❌ Error creating demo database: {e}")
        return False

if __name__ == "__main__":
    success = populate_demo_data()
    if not success:
        exit(1)