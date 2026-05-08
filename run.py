#!/usr/bin/env python3
"""
Louisiana Foundations CRM - Command Line Interface

This script provides easy access to the main functions of the CRM system.
"""

import argparse
import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).parent / "src"))

def main():
    parser = argparse.ArgumentParser(description="Louisiana Foundations CRM")
    parser.add_argument(
        "command",
        choices=["acquire", "webapp", "export", "init"],
        help="Command to run"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (for export command)"
    )
    
    args = parser.parse_args()
    
    if args.command == "init":
        print("🏛️  Initializing Louisiana Foundations CRM")
        print("Creating database structure...")
        
        from data_acquisition import DataAcquisition
        da = DataAcquisition()
        print("✅ Database initialized successfully!")
        print("\nNext steps:")
        print("1. Run 'python run.py acquire' to collect foundation data")
        print("2. Run 'python run.py webapp' to start the CRM interface")
    
    elif args.command == "acquire":
        print("🔍 Starting data acquisition...")
        print("This will fetch foundation data from multiple sources.")
        print("This process may take 10-30 minutes depending on data availability.\n")
        
        from data_acquisition import DataAcquisition
        da = DataAcquisition()
        da.run_full_acquisition()
        print("\n✅ Data acquisition complete!")
        print("Run 'python run.py webapp' to view the results in the CRM interface.")
    
    elif args.command == "webapp":
        print("🚀 Starting CRM web interface...")
        print("The CRM will be available at: http://localhost:8501")
        print("Press Ctrl+C to stop the server.\n")
        
        import subprocess
        try:
            subprocess.run([
                "streamlit", "run", 
                str(Path(__file__).parent / "src" / "crm_app.py"),
                "--server.port", "8501",
                "--server.headless", "true"
            ])
        except KeyboardInterrupt:
            print("\n👋 CRM server stopped.")
        except FileNotFoundError:
            print("❌ Error: Streamlit not found. Please install requirements:")
            print("pip install -r requirements.txt")
    
    elif args.command == "export":
        print("📤 Exporting foundation data...")
        
        from data_acquisition import DataAcquisition
        da = DataAcquisition()
        
        output_path = args.output or "louisiana_foundations.csv"
        df = da.export_to_csv(output_path)
        
        print(f"✅ Exported {len(df)} foundations to {output_path}")

if __name__ == "__main__":
    main()