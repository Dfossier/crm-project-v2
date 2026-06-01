#!/usr/bin/env python3
"""
Enhanced demo script with comprehensive 990 data including:
- Board Members, Officers, Key Employees
- Investment advisors and contract payments
- Detailed financial information from 990 forms
"""

import sqlite3
from pathlib import Path
from datetime import datetime

# Additional Louisiana foundations with comprehensive 990 data
ENHANCED_FOUNDATIONS = [
    {
        'ein': '72-0555001',
        'name': 'The Goldring Family Foundation',
        'legal_name': 'The Goldring Family Foundation Inc.',
        'city': 'New Orleans',
        'state': 'LA',
        'zip_code': '70130',
        'website': 'http://goldringfoundation.org',
        'phone': '(504) 555-0101',
        'investment_assets': 42500000,
        'annual_grants': 2100000,
        'annual_revenue': 3400000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'family'
    },
    {
        'ein': '72-0555002',
        'name': 'Shell Foundation',
        'legal_name': 'Shell Oil Company Foundation',
        'city': 'New Orleans',
        'state': 'LA',
        'zip_code': '70113',
        'website': 'http://shell.com/foundation',
        'phone': '(504) 555-0202',
        'investment_assets': 67000000,
        'annual_grants': 3350000,
        'annual_revenue': 4800000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'corporate'
    },
    {
        'ein': '72-0555003',
        'name': 'The Latter & Blum Foundation',
        'legal_name': 'The Latter & Blum Foundation Inc.',
        'city': 'New Orleans',
        'state': 'LA',
        'zip_code': '70125',
        'website': 'http://latterblum.com/foundation',
        'phone': '(504) 555-0303',
        'investment_assets': 18500000,
        'annual_grants': 925000,
        'annual_revenue': 1600000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'family'
    },
    {
        'ein': '72-0555004',
        'name': 'Coypu Foundation',
        'legal_name': 'The Coypu Foundation',
        'city': 'Lafayette',
        'state': 'LA',
        'zip_code': '70506',
        'website': 'http://coypufoundation.org',
        'phone': '(337) 555-0404',
        'investment_assets': 31000000,
        'annual_grants': 1550000,
        'annual_revenue': 2300000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'private'
    },
    {
        'ein': '72-0555005',
        'name': 'Livingston Parish Community Foundation',
        'legal_name': 'Livingston Parish Community Foundation Inc.',
        'city': 'Livingston',
        'state': 'LA',
        'zip_code': '70754',
        'website': 'http://lpcf.org',
        'phone': '(225) 555-0505',
        'investment_assets': 8500000,
        'annual_grants': 425000,
        'annual_revenue': 780000,
        'filing_year': 2023,
        'tax_exempt_status': '501(c)(3)',
        'foundation_type': 'community'
    }
]

# Comprehensive personnel data including all key 990 roles
ENHANCED_PERSONNEL = {
    'The Goldring Family Foundation': [
        {'name': 'Stephen Goldring', 'title': 'Chairman of the Board', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 5, 'is_voting': True},
        {'name': 'Amy Goldring Sutherland', 'title': 'President', 'role': 'president', 'compensation': 125000, 'hours_per_week': 40, 'is_voting': True},
        {'name': 'Michael Goldring', 'title': 'Vice President', 'role': 'vice_president', 'compensation': 0, 'hours_per_week': 10, 'is_voting': True},
        {'name': 'Jennifer LeBlanc', 'title': 'Secretary', 'role': 'secretary', 'compensation': 75000, 'hours_per_week': 30, 'is_voting': False},
        {'name': 'Robert Martinez', 'title': 'Treasurer/CFO', 'role': 'cfo', 'compensation': 95000, 'hours_per_week': 25, 'is_voting': False},
        {'name': 'David Chen', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 3, 'is_voting': True},
        {'name': 'Sarah Williams', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 3, 'is_voting': True},
        {'name': 'Jennifer LeBlanc', 'title': 'Person Filing 990', 'role': 'filer', 'compensation': 75000, 'hours_per_week': 30, 'is_voting': False}
    ],
    'Shell Foundation': [
        {'name': 'Marcus Johnson', 'title': 'Chairman', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 8, 'is_voting': True},
        {'name': 'Lisa Thompson', 'title': 'President & CEO', 'role': 'president', 'compensation': 185000, 'hours_per_week': 40, 'is_voting': True},
        {'name': 'Carlos Rodriguez', 'title': 'Chief Financial Officer', 'role': 'cfo', 'compensation': 145000, 'hours_per_week': 40, 'is_voting': False},
        {'name': 'Patricia Davis', 'title': 'Secretary', 'role': 'secretary', 'compensation': 85000, 'hours_per_week': 35, 'is_voting': False},
        {'name': 'James Miller', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 4, 'is_voting': True},
        {'name': 'Angela Foster', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 4, 'is_voting': True},
        {'name': 'Robert Kim', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 4, 'is_voting': True},
        {'name': 'Carlos Rodriguez', 'title': 'Person Filing 990', 'role': 'filer', 'compensation': 145000, 'hours_per_week': 40, 'is_voting': False}
    ],
    'The Latter & Blum Foundation': [
        {'name': 'William Latter III', 'title': 'Chairman & President', 'role': 'president', 'compensation': 0, 'hours_per_week': 15, 'is_voting': True},
        {'name': 'Susan Blum Keller', 'title': 'Vice President', 'role': 'vice_president', 'compensation': 0, 'hours_per_week': 10, 'is_voting': True},
        {'name': 'Thomas Anderson', 'title': 'Secretary/Treasurer', 'role': 'cfo', 'compensation': 45000, 'hours_per_week': 20, 'is_voting': False},
        {'name': 'Margaret Latter', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 5, 'is_voting': True},
        {'name': 'Edward Blum Jr.', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 5, 'is_voting': True},
        {'name': 'Thomas Anderson', 'title': 'Person Filing 990', 'role': 'filer', 'compensation': 45000, 'hours_per_week': 20, 'is_voting': False}
    ],
    'Coypu Foundation': [
        {'name': 'Jean-Paul Thibodaux', 'title': 'Chairman', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 6, 'is_voting': True},
        {'name': 'Marie Boudreaux', 'title': 'President', 'role': 'president', 'compensation': 95000, 'hours_per_week': 35, 'is_voting': True},
        {'name': 'Pierre Landry', 'title': 'CFO', 'role': 'cfo', 'compensation': 75000, 'hours_per_week': 30, 'is_voting': False},
        {'name': 'Celeste Guidry', 'title': 'Secretary', 'role': 'secretary', 'compensation': 55000, 'hours_per_week': 25, 'is_voting': False},
        {'name': 'Antoine Hebert', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 4, 'is_voting': True},
        {'name': 'Evangeline Broussard', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 4, 'is_voting': True},
        {'name': 'Pierre Landry', 'title': 'Person Filing 990', 'role': 'filer', 'compensation': 75000, 'hours_per_week': 30, 'is_voting': False}
    ],
    'Livingston Parish Community Foundation': [
        {'name': 'Robert Edwards', 'title': 'Chairman of the Board', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 8, 'is_voting': True},
        {'name': 'Linda Watson', 'title': 'Executive Director', 'role': 'president', 'compensation': 65000, 'hours_per_week': 40, 'is_voting': True},
        {'name': 'Mark Stevens', 'title': 'Treasurer', 'role': 'cfo', 'compensation': 35000, 'hours_per_week': 20, 'is_voting': False},
        {'name': 'Carol Johnson', 'title': 'Secretary', 'role': 'secretary', 'compensation': 28000, 'hours_per_week': 15, 'is_voting': False},
        {'name': 'James Parker', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 3, 'is_voting': True},
        {'name': 'Mary Collins', 'title': 'Board Member', 'role': 'board_member', 'compensation': 0, 'hours_per_week': 3, 'is_voting': True},
        {'name': 'Linda Watson', 'title': 'Person Filing 990', 'role': 'filer', 'compensation': 65000, 'hours_per_week': 40, 'is_voting': True}
    ]
}

# Investment advisor contract payments (Part VII-B of Form 990-PF)
INVESTMENT_ADVISORS = [
    {
        'foundation': 'The Goldring Family Foundation',
        'advisor_name': 'Merrill Lynch Wealth Management',
        'advisor_ein': '13-2740599',
        'services': 'Investment management and advisory services',
        'annual_fee': 485000,
        'fee_type': 'percentage_of_assets',
        'fee_percentage': 1.15,
        'contract_start': '2019-01-01',
        'assets_managed': 42500000
    },
    {
        'foundation': 'Shell Foundation',
        'advisor_name': 'BlackRock Institutional Trust Company',
        'advisor_ein': '13-5832595',
        'services': 'Investment advisory and fund management',
        'annual_fee': 735000,
        'fee_type': 'percentage_of_assets',
        'fee_percentage': 1.10,
        'contract_start': '2017-03-15',
        'assets_managed': 67000000
    },
    {
        'foundation': 'The Latter & Blum Foundation',
        'advisor_name': 'Morgan Stanley Private Wealth Management',
        'advisor_ein': '13-2923929',
        'services': 'Portfolio management and investment advisory',
        'annual_fee': 220000,
        'fee_type': 'percentage_of_assets',
        'fee_percentage': 1.20,
        'contract_start': '2020-07-01',
        'assets_managed': 18500000
    },
    {
        'foundation': 'Coypu Foundation',
        'advisor_name': 'Raymond James Investment Services',
        'advisor_ein': '59-1225164',
        'services': 'Investment advisory and wealth management',
        'annual_fee': 325000,
        'fee_type': 'percentage_of_assets',
        'fee_percentage': 1.05,
        'contract_start': '2018-09-01',
        'assets_managed': 31000000
    },
    {
        'foundation': 'Livingston Parish Community Foundation',
        'advisor_name': 'Edward Jones Financial Services',
        'advisor_ein': '43-0851979',
        'services': 'Investment management for endowment funds',
        'annual_fee': 95000,
        'fee_type': 'percentage_of_assets',
        'fee_percentage': 1.12,
        'contract_start': '2021-01-01',
        'assets_managed': 8500000
    }
]

def add_enhanced_data():
    """Add enhanced foundation data with comprehensive 990 information."""
    
    base_dir = Path(__file__).parent
    db_path = base_dir / "database" / "louisiana_foundations.db"
    
    print("🔧 Adding Enhanced Foundation Data")
    print("=" * 50)
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Add new foundations
            foundation_ids = {}
            
            print("🏛️  Adding additional foundations...")
            for foundation in ENHANCED_FOUNDATIONS:
                cursor.execute("""
                    INSERT OR REPLACE INTO foundations 
                    (ein, name, legal_name, city, state, zip_code, website, phone,
                     investment_assets, annual_grants, annual_revenue, filing_year,
                     tax_exempt_status, foundation_type, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 
                            datetime('now'), datetime('now'))
                """, (
                    foundation['ein'], foundation['name'], foundation['legal_name'],
                    foundation['city'], foundation['state'], foundation['zip_code'],
                    foundation['website'], foundation['phone'], foundation['investment_assets'],
                    foundation['annual_grants'], foundation['annual_revenue'],
                    foundation['filing_year'], foundation['tax_exempt_status'],
                    foundation['foundation_type']
                ))
                
                foundation_ids[foundation['name']] = cursor.lastrowid
                print(f"   Added: {foundation['name']} (${foundation['investment_assets']/1e6:.1f}M)")
            
            # Add comprehensive personnel data
            print("\n👥 Adding comprehensive personnel (Board, Officers, Key Staff)...")
            
            # First, get existing foundation IDs
            cursor.execute("SELECT id, name FROM foundations")
            existing_foundations = {name: id for id, name in cursor.fetchall()}
            foundation_ids.update(existing_foundations)
            
            for foundation_name, personnel_list in ENHANCED_PERSONNEL.items():
                if foundation_name in foundation_ids:
                    foundation_id = foundation_ids[foundation_name]
                    
                    for person in personnel_list:
                        cursor.execute("""
                            INSERT INTO personnel 
                            (foundation_id, name, title, role, compensation, hours_per_week, is_current)
                            VALUES (?, ?, ?, ?, ?, ?, 1)
                        """, (
                            foundation_id, person['name'], person['title'], 
                            person['role'], person['compensation'], person['hours_per_week']
                        ))
                    
                    print(f"   Added {len(personnel_list)} personnel for {foundation_name}")
            
            # Create investment advisors table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS investment_advisors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    foundation_id INTEGER,
                    advisor_name TEXT NOT NULL,
                    advisor_ein TEXT,
                    services TEXT,
                    annual_fee REAL,
                    fee_type TEXT,
                    fee_percentage REAL,
                    contract_start DATE,
                    assets_managed REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (foundation_id) REFERENCES foundations(id)
                )
            """)
            
            # Add investment advisor data
            print("\n💼 Adding investment advisor contract information...")
            for advisor in INVESTMENT_ADVISORS:
                if advisor['foundation'] in foundation_ids:
                    foundation_id = foundation_ids[advisor['foundation']]
                    
                    cursor.execute("""
                        INSERT INTO investment_advisors
                        (foundation_id, advisor_name, advisor_ein, services, annual_fee,
                         fee_type, fee_percentage, contract_start, assets_managed)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        foundation_id, advisor['advisor_name'], advisor['advisor_ein'],
                        advisor['services'], advisor['annual_fee'], advisor['fee_type'],
                        advisor['fee_percentage'], advisor['contract_start'],
                        advisor['assets_managed']
                    ))
                    
                    print(f"   Added: {advisor['advisor_name']} for {advisor['foundation']} (${advisor['annual_fee']:,}/year)")
            
            conn.commit()
            
            # Display enhanced summary
            print("\n📊 Enhanced Database Summary:")
            cursor.execute("SELECT COUNT(*) FROM foundations")
            foundation_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(investment_assets) FROM foundations")
            total_assets = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(annual_grants) FROM foundations")
            total_grants = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM personnel")
            personnel_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM investment_advisors")
            advisor_count = cursor.fetchone()[0]
            
            print(f"   Foundations: {foundation_count}")
            print(f"   Total Assets: ${total_assets/1e6:.0f}M")
            print(f"   Annual Grants: ${total_grants/1e6:.0f}M")
            print(f"   Personnel Records: {personnel_count}")
            print(f"   Investment Advisors: {advisor_count}")
            
            # Personnel breakdown
            print("\n👥 Personnel by Role:")
            cursor.execute("SELECT role, COUNT(*) FROM personnel GROUP BY role ORDER BY COUNT(*) DESC")
            for row in cursor.fetchall():
                print(f"   {row[0].replace('_', ' ').title()}: {row[1]}")
            
            # Investment advisor fees
            print("\n💰 Total Investment Advisory Fees:")
            cursor.execute("SELECT SUM(annual_fee) FROM investment_advisors")
            total_fees = cursor.fetchone()[0]
            print(f"   Total Annual Fees: ${total_fees:,}")
            
            print("\n✅ Enhanced data added successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Error adding enhanced data: {e}")
        return False

if __name__ == "__main__":
    success = add_enhanced_data()
    if not success:
        exit(1)