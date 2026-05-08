#!/usr/bin/env python3
"""
Run real data acquisition for Louisiana foundations.
This clears demo data and fetches real foundation information.
"""

import sqlite3
import sys
from pathlib import Path
import logging

# Add src directory to path
sys.path.append(str(Path(__file__).parent / "src"))

from data_acquisition import DataAcquisition

def clear_existing_data(db_path):
    """Clear all existing foundation data."""
    print("🧹 Clearing existing demo data...")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Clear in proper order due to foreign key constraints
        cursor.execute("DELETE FROM interactions")
        cursor.execute("DELETE FROM grants")
        cursor.execute("DELETE FROM investment_advisors") 
        cursor.execute("DELETE FROM focus_areas")
        cursor.execute("DELETE FROM personnel")
        cursor.execute("DELETE FROM financial_history")
        cursor.execute("DELETE FROM data_sources")
        cursor.execute("DELETE FROM foundations")
        
        # Reset auto-increment
        cursor.execute("DELETE FROM sqlite_sequence")
        
        conn.commit()
        
    print("✅ Demo data cleared")

def main():
    print("🏛️  Louisiana Foundation CRM - Real Data Acquisition")
    print("=" * 60)
    print("This will replace demo data with real foundation data from:")
    print("- ProPublica Nonprofit Explorer API")
    print("- IRS data sources") 
    print("- Additional foundation databases")
    print()
    
    # Initialize data acquisition
    da = DataAcquisition()
    
    # Clear existing demo data
    clear_existing_data(da.db_path)
    
    # Run comprehensive acquisition
    print("🔍 Starting comprehensive data acquisition...")
    print("This may take 15-30 minutes to gather complete data.")
    print()
    
    try:
        # Set up more detailed logging
        logging.basicConfig(level=logging.INFO)
        
        # Run the full acquisition
        da.run_full_acquisition()
        
        # Check results
        with sqlite3.connect(da.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM foundations WHERE investment_assets >= 2000000")
            foundation_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(investment_assets) FROM foundations WHERE investment_assets >= 2000000")
            total_assets = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT SUM(annual_grants) FROM foundations WHERE investment_assets >= 2000000")
            total_grants = cursor.fetchone()[0] or 0
        
        print("\n🎉 Real Data Acquisition Complete!")
        print(f"   Foundations with >$2M assets: {foundation_count}")
        print(f"   Total assets: ${total_assets/1e6:.0f}M")
        print(f"   Total annual grants: ${total_grants/1e6:.0f}M")
        
        if foundation_count == 0:
            print("\n⚠️  No foundations found with >$2M assets.")
            print("This might mean:")
            print("- The asset filter is too restrictive")
            print("- API data doesn't include asset information") 
            print("- Additional data enrichment is needed")
            print("\nConsider running enhanced_demo_data.py for sample data.")
        
    except Exception as e:
        print(f"❌ Error during acquisition: {e}")
        print("\nFalling back to demo data...")
        import subprocess
        subprocess.run([sys.executable, "enhanced_demo_data.py"])

if __name__ == "__main__":
    main()