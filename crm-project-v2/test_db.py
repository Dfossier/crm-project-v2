#!/usr/bin/env python3
"""
Test script to verify database schema and basic functionality
"""

import sqlite3
from pathlib import Path

def test_database():
    """Test database creation and schema."""
    
    # Paths
    base_dir = Path(__file__).parent
    schema_path = base_dir / "database" / "schema.sql"
    db_path = base_dir / "database" / "test.db"
    
    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Remove existing test db
    if db_path.exists():
        db_path.unlink()
    
    print("🗄️  Testing database schema...")
    
    try:
        # Create database and apply schema
        with sqlite3.connect(db_path) as conn:
            with open(schema_path, 'r') as f:
                conn.executescript(f.read())
            
            print("✅ Database schema applied successfully!")
            
            # Test inserting a sample foundation
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO foundations 
                (ein, name, legal_name, city, state, investment_assets, annual_grants)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                "72-1234567", 
                "Test Foundation", 
                "Test Foundation Inc.", 
                "New Orleans", 
                "LA", 
                5000000,  # $5M assets
                250000    # $250K grants
            ))
            
            # Verify insertion
            cursor.execute("SELECT COUNT(*) FROM foundations")
            count = cursor.fetchone()[0]
            
            if count == 1:
                print("✅ Sample data inserted successfully!")
            else:
                print("❌ Error inserting sample data")
                return False
            
            # Test the view
            cursor.execute("SELECT * FROM foundations_summary")
            result = cursor.fetchone()
            
            if result:
                print("✅ Database views working correctly!")
                print(f"   Sample foundation: {result[2]} in {result[3]}")
                print(f"   Assets: ${result[4]:,}")
            
            # Test constraints
            try:
                cursor.execute("""
                    INSERT INTO foundations 
                    (ein, name, investment_assets)
                    VALUES (?, ?, ?)
                """, ("72-9999999", "Small Foundation", 1000000))  # Only $1M - should fail
                print("❌ Constraint not working - small foundation was inserted")
                return False
            except sqlite3.IntegrityError:
                print("✅ Asset threshold constraint working correctly!")
            
            conn.commit()
        
        print("\n🎉 All database tests passed!")
        
        # Clean up
        db_path.unlink()
        
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_database()
    if not success:
        exit(1)