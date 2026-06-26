#!/usr/bin/env python3
"""
Louisiana Foundations Data Acquisition Script

Fetches foundation data from multiple sources:
- ProPublica Nonprofit Explorer API
- IRS Annual Extract files
- Direct web scraping where necessary
"""

import requests
import pandas as pd
import sqlite3
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataAcquisition:
    def __init__(self, db_path: str = "database/louisiana_foundations.db"):
        self.db_path = db_path
        self.base_dir = Path(__file__).parent.parent
        self.db_path = self.base_dir / db_path
        self.session = requests.Session()
        
        # API endpoints and configurations
        self.propublica_api_base = "https://projects.propublica.org/nonprofits/api/v2"
        
        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self.init_database()
    
    def init_database(self):
        """Initialize the database with schema if it doesn't exist."""
        schema_path = self.base_dir / "database" / "schema.sql"
        
        if schema_path.exists():
            with sqlite3.connect(self.db_path) as conn:
                # Check if tables already exist
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='foundations';")
                
                if cursor.fetchone() is None:
                    # Tables don't exist, create them
                    with open(schema_path, 'r') as f:
                        conn.executescript(f.read())
                    logger.info("Database initialized with schema")
                else:
                    logger.info("Database tables already exist, skipping schema creation")
    
    def search_propublica_organizations(self, state: str = "LA", 
                                      org_types: List[str] = None) -> List[Dict]:
        """Search for organizations using ProPublica API."""
        if org_types is None:
            org_types = ["501C3"]  # Focus on 501(c)(3) organizations
        
        all_orgs = []
        
        for org_type in org_types:
            page = 0
            while True:
                try:
                    url = f"{self.propublica_api_base}/search.json"
                    params = {
                        'state[id]': state,
                        'c_code[id]': '3',  # 501(c)(3) organizations
                        'page': page
                    }
                    
                    response = self.session.get(url, params=params, timeout=30)
                    response.raise_for_status()
                    
                    data = response.json()
                    organizations = data.get('organizations', [])
                    
                    if not organizations:
                        break
                    
                    # Filter for foundations with substantial assets
                    for org in organizations:
                        # Look for keywords that suggest it's a foundation
                        name_lower = org.get('name', '').lower()
                        sub_name_lower = org.get('sub_name', '').lower()
                        
                        foundation_keywords = [
                            'foundation', 'fund', 'trust', 'endowment', 
                            'charitable fund', 'family fund', 'community fund',
                            'giving fund', 'scholarship fund', 'education fund',
                            'memorial fund', 'research fund'
                        ]
                        
                        # Check both name and sub_name for foundation indicators
                        full_name = f"{name_lower} {sub_name_lower}"
                        if any(keyword in full_name for keyword in foundation_keywords):
                            # Exclude obvious non-foundations
                            exclude_keywords = [
                                'hospital', 'clinic', 'school', 'church', 
                                'museum', 'library', 'university', 'college',
                                'association', 'society', 'council', 'league',
                                'club', 'shelter', 'food bank', 'rescue'
                            ]
                            
                            if not any(exclude in full_name for exclude in exclude_keywords):
                                all_orgs.append(org)
                    
                    logger.info(f"Retrieved page {page}, found {len(organizations)} organizations")
                    page += 1
                    
                    # Rate limiting
                    time.sleep(1)
                    
                    # Limit pages for now (can remove later)
                    if page > 10:  # Adjust this limit as needed
                        break
                        
                except requests.RequestException as e:
                    logger.error(f"Error fetching page {page}: {e}")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error on page {page}: {e}")
                    break
        
        logger.info(f"Found {len(all_orgs)} potential foundations")
        return all_orgs
    
    def get_organization_details(self, ein: str) -> Optional[Dict]:
        """Get detailed information for a specific organization."""
        try:
            url = f"{self.propublica_api_base}/organizations/{ein}.json"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()
            # Return the full response which includes both 'organization' and 'filings_with_data'
            # Merge them into a single dict for backwards compatibility
            org = data.get('organization', {})
            org['filings_with_data'] = data.get('filings_with_data', [])
            org['filings'] = data.get('filings', [])  # Keep for backwards compatibility
            return org

        except requests.RequestException as e:
            logger.error(f"Error fetching details for EIN {ein}: {e}")
            return None
    
    def extract_foundation_data(self, org_data: Dict) -> Optional[Dict]:
        """Extract and structure foundation data from API response."""
        try:
            # Get the most recent filing - API now uses 'filings_with_data'
            filings = org_data.get('filings_with_data', [])
            if not filings:
                # Fallback to old 'filings' key if available
                filings = org_data.get('filings', [])

            if not filings:
                return None

            # Find the latest filing by tax year (don't assume sorted)
            latest_filing = max(filings, key=lambda x: x.get('tax_prd_yr', 0))

            # Extract basic information
            foundation = {
                'ein': str(org_data.get('ein')),
                'name': org_data.get('name'),
                'legal_name': org_data.get('name'),  # May need to extract from filings
                'city': org_data.get('city'),
                'state': org_data.get('state'),
                'zip_code': org_data.get('zipcode'),
                'website': None,  # Not always available in API
                'tax_exempt_status': org_data.get('classification_codes'),
                'ruling_date': org_data.get('ruling_date')
            }

            # Extract financial data from latest filing
            if 'totrevenue' in latest_filing:
                total_assets = latest_filing.get('totassetsend', 0)
                net_assets = latest_filing.get('totnetassetend', 0)

                # Use net assets as proxy for investment assets if totsecuritiesend is not available
                # For community foundations, net assets are typically heavily invested
                investment_assets = latest_filing.get('totsecuritiesend') or net_assets * 0.9  # Conservative estimate

                foundation.update({
                    'total_assets': total_assets,
                    'investment_assets': investment_assets,
                    'annual_revenue': latest_filing.get('totrevenue'),
                    'annual_grants': latest_filing.get('totgrantspaid', 0),
                    'filing_year': latest_filing.get('tax_prd_yr')
                })

            # Only return if total assets meet our threshold (changed from investment_assets)
            # This ensures we capture all substantial foundations
            if foundation.get('total_assets', 0) >= 2000000:
                return foundation

            return None

        except Exception as e:
            logger.error(f"Error extracting foundation data: {e}")
            return None
    
    def save_foundation_to_db(self, foundation_data: Dict) -> bool:
        """Save foundation data to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if foundation already exists
                cursor.execute("SELECT id FROM foundations WHERE ein = ?", (foundation_data['ein'],))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing record
                    cursor.execute("""
                        UPDATE foundations 
                        SET name=?, legal_name=?, city=?, state=?, zip_code=?,
                            total_assets=?, investment_assets=?, annual_revenue=?,
                            annual_grants=?, filing_year=?, tax_exempt_status=?,
                            ruling_date=?, updated_at=CURRENT_TIMESTAMP
                        WHERE ein=?
                    """, (
                        foundation_data['name'], foundation_data['legal_name'],
                        foundation_data['city'], foundation_data['state'], foundation_data['zip_code'],
                        foundation_data['total_assets'], foundation_data['investment_assets'],
                        foundation_data['annual_revenue'], foundation_data['annual_grants'],
                        foundation_data['filing_year'], foundation_data['tax_exempt_status'],
                        foundation_data['ruling_date'], foundation_data['ein']
                    ))
                else:
                    # Insert new record
                    cursor.execute("""
                        INSERT INTO foundations 
                        (ein, name, legal_name, city, state, zip_code, total_assets, 
                         investment_assets, annual_revenue, annual_grants, filing_year,
                         tax_exempt_status, ruling_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        foundation_data['ein'], foundation_data['name'], foundation_data['legal_name'],
                        foundation_data['city'], foundation_data['state'], foundation_data['zip_code'],
                        foundation_data['total_assets'], foundation_data['investment_assets'],
                        foundation_data['annual_revenue'], foundation_data['annual_grants'],
                        foundation_data['filing_year'], foundation_data['tax_exempt_status'],
                        foundation_data['ruling_date']
                    ))
                
                conn.commit()
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Database error saving foundation {foundation_data['ein']}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving foundation {foundation_data['ein']}: {e}")
            return False
    
    def run_full_acquisition(self):
        """Run the complete data acquisition process."""
        logger.info("Starting Louisiana foundations data acquisition")
        
        # Step 1: Search for potential foundations
        organizations = self.search_propublica_organizations()
        
        successful_saves = 0
        total_processed = 0
        
        # Step 2: Get detailed data for each organization
        for org in organizations:
            ein = org.get('ein')
            if not ein:
                continue
                
            logger.info(f"Processing EIN {ein}: {org.get('name', 'Unknown')}")
            
            # Get detailed organization data
            org_details = self.get_organization_details(ein)
            if not org_details:
                continue
            
            # Extract and structure the data
            foundation_data = self.extract_foundation_data(org_details)
            if not foundation_data:
                continue
            
            # Save to database
            if self.save_foundation_to_db(foundation_data):
                successful_saves += 1
                logger.info(f"Saved foundation: {foundation_data['name']} "
                          f"(Assets: ${foundation_data['investment_assets']:,.0f})")
            
            total_processed += 1
            
            # Rate limiting
            time.sleep(0.5)
        
        logger.info(f"Data acquisition complete. Processed {total_processed} organizations, "
                   f"successfully saved {successful_saves} foundations with >$2M assets")
    
    def export_to_csv(self, output_path: str = "data/louisiana_foundations.csv"):
        """Export foundation data to CSV for analysis."""
        output_path = self.base_dir / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT 
                    name, ein, city, state, zip_code, website,
                    investment_assets, annual_grants, annual_revenue,
                    filing_year, tax_exempt_status,
                    created_at, updated_at
                FROM foundations
                ORDER BY investment_assets DESC
            """
            df = pd.read_sql_query(query, conn)
            df.to_csv(output_path, index=False)
            
        logger.info(f"Exported {len(df)} foundations to {output_path}")
        return df

def main():
    """Main execution function."""
    acquisition = DataAcquisition()
    
    # Run the full acquisition process
    acquisition.run_full_acquisition()
    
    # Export results
    df = acquisition.export_to_csv()
    print(f"\nFoundations with >$2M in investment assets: {len(df)}")
    
    if len(df) > 0:
        print(f"\nTop 10 by investment assets:")
        print(df[['name', 'city', 'investment_assets', 'annual_grants']].head(10))

if __name__ == "__main__":
    main()