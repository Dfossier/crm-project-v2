#!/usr/bin/env python3
"""
Check what data is stored and where in the Foundation CRM.
"""

import sqlite3
import os
from pathlib import Path

def check_database():
    """Examine the database structure and contents."""
    
    db_path = Path(__file__).parent / "database" / "louisiana_foundations.db"
    
    print("📊 FOUNDATION CRM DATA STORAGE ANALYSIS")
    print("=" * 55)
    
    # File info
    print(f"📁 Database Location: {db_path}")
    print(f"📏 Database Size: {os.path.getsize(db_path) / 1024:.1f} KB")
    print()
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Show table structure
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        print("📋 DATABASE TABLES:")
        for table in tables:
            if table == 'sqlite_sequence':
                continue
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   {table}: {count:,} records")
        
        print()
        print("🏛️ FOUNDATION DATA SAMPLE:")
        cursor.execute("""
            SELECT name, investment_assets, city, ein, website, phone 
            FROM foundations 
            WHERE investment_assets >= 2000000 
            ORDER BY investment_assets DESC 
            LIMIT 5
        """)
        
        for i, (name, assets, city, ein, website, phone) in enumerate(cursor.fetchall(), 1):
            print(f"   {i}. {name}")
            print(f"      • Assets: ${assets/1e6:.1f}M | City: {city}")
            print(f"      • EIN: {ein}")
            if website:
                print(f"      • Website: {website}")
            if phone:
                print(f"      • Phone: {phone}")
            print()
        
        # Personnel data
        print("👥 PERSONNEL DATA SAMPLE:")
        cursor.execute("""
            SELECT f.name, p.name, p.title, p.role, p.compensation 
            FROM personnel p 
            JOIN foundations f ON p.foundation_id = f.id 
            ORDER BY p.compensation DESC
            LIMIT 5
        """)
        
        personnel = cursor.fetchall()
        if personnel:
            for fname, pname, title, role, comp in personnel:
                comp_str = f"${comp:,}" if comp > 0 else "No compensation"
                print(f"   • {pname} - {title}")
                print(f"     Role: {role.replace('_', ' ').title()} | Compensation: {comp_str}")
                print(f"     Foundation: {fname}")
                print()
        else:
            print("   No personnel data found")
        
        # Investment advisors
        cursor.execute("SELECT COUNT(*) FROM investment_advisors")
        advisor_count = cursor.fetchone()[0]
        
        if advisor_count > 0:
            print("💼 INVESTMENT ADVISOR DATA:")
            cursor.execute("""
                SELECT f.name, ia.advisor_name, ia.annual_fee, ia.assets_managed 
                FROM investment_advisors ia 
                JOIN foundations f ON ia.foundation_id = f.id 
                ORDER BY ia.annual_fee DESC
                LIMIT 3
            """)
            
            for fname, advisor, fee, managed in cursor.fetchall():
                print(f"   • {advisor}")
                print(f"     Client: {fname}")
                print(f"     Annual Fee: ${fee:,}")
                print(f"     Assets Managed: ${managed/1e6:.1f}M")
                print()
        
        # Data totals
        print("📊 DATA SUMMARY:")
        cursor.execute("SELECT COUNT(*) FROM foundations WHERE investment_assets >= 2000000")
        qualifying = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(investment_assets), SUM(annual_grants) FROM foundations WHERE investment_assets >= 2000000")
        total_assets, total_grants = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) FROM personnel")
        personnel_count = cursor.fetchone()[0]
        
        print(f"   • Qualifying Foundations: {qualifying:,}")
        print(f"   • Total Assets: ${total_assets/1e6:.0f}M")
        print(f"   • Total Annual Grants: ${total_grants/1e6:.0f}M")
        print(f"   • Personnel Records: {personnel_count:,}")
        print(f"   • Investment Advisors: {advisor_count:,}")

def check_files():
    """Check what other files are stored."""
    
    print("\n📁 FILE STORAGE:")
    print("-" * 30)
    
    base_dir = Path(__file__).parent
    
    # Important files
    important_files = [
        "database/louisiana_foundations.db",
        "foundation_dashboard.html",
        "streamlit.log",
        "crm.pid"
    ]
    
    for file_path in important_files:
        full_path = base_dir / file_path
        if full_path.exists():
            size = os.path.getsize(full_path)
            print(f"   ✅ {file_path} ({size:,} bytes)")
        else:
            print(f"   ❌ {file_path} (not found)")
    
    # Check for any PDF files (990 forms)
    pdf_files = list(base_dir.rglob("*.pdf"))
    if pdf_files:
        print(f"\n📄 PDF FILES FOUND:")
        for pdf in pdf_files[:10]:  # Show first 10
            print(f"   • {pdf.relative_to(base_dir)} ({os.path.getsize(pdf):,} bytes)")
    else:
        print(f"\n📄 PDF FILES: None found (990 forms not downloaded)")

def data_source_explanation():
    """Explain what data we have and where it came from."""
    
    print("\n🔍 DATA SOURCES & WHAT'S STORED:")
    print("-" * 45)
    
    print("""
📊 FOUNDATION DISCOVERY:
   ✅ Real foundation names from ProPublica Nonprofit Explorer API
   ✅ Basic info: Name, EIN, City, State from official databases
   ✅ Foundation type classification (private, community, corporate)

💰 FINANCIAL DATA:
   ⚠️  Asset amounts are REALISTIC ESTIMATES, not actual 990 data
   ⚠️  Based on foundation size tiers and industry research
   ⚠️  Payout rates calculated using typical foundation ratios

👥 PERSONNEL DATA:
   ⚠️  Names, titles, compensation are SAMPLE DATA
   ⚠️  Realistic roles (President, CFO, Board Members) with typical pay
   ⚠️  Structure matches what you'd find in real 990 forms

💼 INVESTMENT ADVISORS:
   ⚠️  Advisor names and fees are SAMPLE DATA
   ⚠️  Based on typical institutional investment management

📋 WHAT'S NOT STORED:
   ❌ Actual Form 990 PDF files
   ❌ Real individual compensation data
   ❌ Actual grant recipient lists
   ❌ Real board member names
   
🎯 WHAT THIS GIVES YOU:
   ✅ Complete foundation discovery for Louisiana
   ✅ Professional CRM interface for prospect research
   ✅ Realistic data structure for demonstration
   ✅ Framework to add real data when available
""")

if __name__ == "__main__":
    check_database()
    check_files()
    data_source_explanation()