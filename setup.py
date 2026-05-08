#!/usr/bin/env python3
"""
Setup script for Louisiana Foundations CRM
"""

import subprocess
import sys
import os
from pathlib import Path

def install_requirements():
    """Install required Python packages."""
    print("📦 Installing required packages...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        print("✅ Requirements installed successfully!")
        return True
    except subprocess.CalledProcessError:
        print("❌ Error installing requirements!")
        return False

def setup_database():
    """Initialize the database."""
    print("🗄️  Setting up database...")
    try:
        from src.data_acquisition import DataAcquisition
        da = DataAcquisition()
        print("✅ Database setup complete!")
        return True
    except Exception as e:
        print(f"❌ Error setting up database: {e}")
        return False

def create_directories():
    """Create necessary directories."""
    print("📁 Creating directory structure...")
    directories = [
        "data",
        "database",
        "exports",
        "logs"
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"   Created: {directory}/")
    
    print("✅ Directory structure created!")

def main():
    print("🏛️  Louisiana Foundations CRM Setup")
    print("=" * 50)
    
    # Create directories
    create_directories()
    
    # Install requirements
    if not install_requirements():
        sys.exit(1)
    
    # Setup database
    if not setup_database():
        print("⚠️  Warning: Database setup failed. You can try running 'python run.py init' later.")
    
    print("\n✅ Setup complete!")
    print("\n🚀 Next steps:")
    print("1. Run data acquisition: python run.py acquire")
    print("2. Start the web interface: python run.py webapp")
    print("3. Or export data: python run.py export")
    
    print("\n📖 For more information, see README.md")

if __name__ == "__main__":
    main()