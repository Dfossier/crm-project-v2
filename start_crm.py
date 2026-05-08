#!/usr/bin/env python3
"""
Proper startup script for Louisiana Foundation CRM with cleanup.
"""

import subprocess
import sys
import os
import signal
import time
from pathlib import Path

def cleanup_processes():
    """Kill any existing streamlit processes."""
    print("🧹 Cleaning up existing processes...")
    
    try:
        # Find and kill streamlit processes
        result = subprocess.run(['pgrep', '-f', 'streamlit'], capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    print(f"   Killing streamlit process {pid}")
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        time.sleep(1)
                        os.kill(int(pid), signal.SIGKILL)
                    except (ProcessLookupError, ValueError):
                        pass
        
        # Also check for any crm_app processes
        result = subprocess.run(['pgrep', '-f', 'crm_app.py'], capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    print(f"   Killing crm_app process {pid}")
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        time.sleep(1)
                        os.kill(int(pid), signal.SIGKILL)
                    except (ProcessLookupError, ValueError):
                        pass
                        
    except Exception as e:
        print(f"   Cleanup warning: {e}")
    
    # Wait a moment for cleanup
    time.sleep(2)
    print("✅ Process cleanup complete")

def check_database():
    """Verify the database has data."""
    import sqlite3
    
    db_path = Path(__file__).parent / "database" / "louisiana_foundations.db"
    
    if not db_path.exists():
        print("❌ Database not found!")
        return False
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM foundations")
            count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM foundations WHERE investment_assets >= 2000000")
            qualifying = cursor.fetchone()[0]
            
            print(f"📊 Database Status: {count} total foundations, {qualifying} with >$2M assets")
            
            if count == 0:
                print("⚠️  Database is empty - consider running comprehensive_acquisition.py first")
                return False
            
            return True
            
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def start_streamlit():
    """Start streamlit with proper configuration."""
    print("🚀 Starting Foundation CRM...")
    
    # Change to correct directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Activate virtual environment and start streamlit
    venv_python = script_dir / "venv" / "bin" / "python"
    app_path = script_dir / "src" / "crm_app.py"
    
    if not venv_python.exists():
        print("❌ Virtual environment not found!")
        return False
    
    if not app_path.exists():
        print("❌ CRM app not found!")
        return False
    
    try:
        # Start streamlit with proper config
        cmd = [
            str(venv_python), "-m", "streamlit", "run", 
            str(app_path),
            "--server.port", "8503",  # Use different port
            "--server.headless", "true",
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "false"
        ]
        
        print(f"   Command: {' '.join(cmd)}")
        print("   Starting on port 8503...")
        
        # Start process
        process = subprocess.Popen(cmd)
        
        # Wait a moment for startup
        time.sleep(3)
        
        # Check if process is still running
        if process.poll() is None:
            print("✅ CRM started successfully!")
            print("   Local URL: http://localhost:8503")
            print("   Press Ctrl+C to stop")
            
            try:
                process.wait()
            except KeyboardInterrupt:
                print("\n🛑 Shutting down...")
                process.terminate()
                time.sleep(2)
                if process.poll() is None:
                    process.kill()
                print("✅ CRM stopped cleanly")
            
            return True
        else:
            print(f"❌ Process failed to start (exit code: {process.returncode})")
            return False
            
    except Exception as e:
        print(f"❌ Failed to start: {e}")
        return False

def main():
    print("🏛️  Louisiana Foundation CRM - Startup Manager")
    print("=" * 55)
    
    # Step 1: Cleanup
    cleanup_processes()
    
    # Step 2: Check database
    if not check_database():
        print("\n💡 Run this first to populate database:")
        print("   python3 comprehensive_acquisition.py")
        return
    
    # Step 3: Start CRM
    start_streamlit()

if __name__ == "__main__":
    main()