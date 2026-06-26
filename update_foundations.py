#!/usr/bin/env python3
"""
Update existing foundations with latest 990 data from ProPublica API
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from data_acquisition import DataAcquisition
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def update_all_foundations():
    """Update all foundations in database with latest data."""
    acquisition = DataAcquisition()

    # Get all foundations from database
    with sqlite3.connect(acquisition.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ein, name FROM foundations")
        foundations = cursor.fetchall()

    logger.info(f"Found {len(foundations)} foundations to update")

    updated_count = 0
    failed_count = 0

    for ein, name in foundations:
        try:
            logger.info(f"Updating {name} (EIN: {ein})")

            # Get latest data from ProPublica
            org_details = acquisition.get_organization_details(ein)
            if not org_details:
                logger.warning(f"Could not fetch data for {ein}")
                failed_count += 1
                continue

            # Extract updated foundation data
            foundation_data = acquisition.extract_foundation_data(org_details)
            if not foundation_data:
                logger.warning(f"Could not extract data for {ein}")
                failed_count += 1
                continue

            # Save to database (will update existing record)
            if acquisition.save_foundation_to_db(foundation_data):
                logger.info(f"✓ Updated {name}: Filing Year {foundation_data['filing_year']}, "
                          f"Assets ${foundation_data['total_assets']:,.0f}")
                updated_count += 1
            else:
                logger.error(f"Failed to save {name}")
                failed_count += 1

            # Rate limiting
            import time
            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error updating {name}: {e}")
            failed_count += 1

    logger.info(f"\nUpdate complete:")
    logger.info(f"  Successfully updated: {updated_count}")
    logger.info(f"  Failed: {failed_count}")

if __name__ == "__main__":
    update_all_foundations()
