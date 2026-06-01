#!/usr/bin/env python3
"""Export CRM data to CSV files for Excel/Spreadsheet use."""

import sqlite3
import csv
import os
from datetime import datetime

# Create exports directory
os.makedirs('exports', exist_ok=True)

conn = sqlite3.connect('database/louisiana_foundations.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. Export Foundations
print("Exporting foundations...")
cur.execute('''
    SELECT id, name, city, state, zip_code, website, email, phone,
           investment_assets, annual_grants, total_assets, ein
    FROM foundations
    ORDER BY investment_assets DESC
''')

with open('exports/foundations.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['ID', 'Name', 'City', 'State', 'ZIP', 'Website', 'Email', 'Phone', 
                     'Investment Assets', 'Annual Grants', 'Total Assets', 'EIN'])
    for row in cur.fetchall():
        payout_pct = ""
        if row['investment_assets'] and row['annual_grants']:
            payout = (row['annual_grants'] / row['investment_assets']) * 100
            payout_pct = f"{payout:.1f}%"
        
        writer.writerow([
            row['id'], row['name'], row['city'], row['state'], row['zip_code'],
            row['website'], row['email'], row['phone'],
            f"${row['investment_assets']:,.0f}" if row['investment_assets'] else "",
            f"${row['annual_grants']:,.0f}" if row['annual_grants'] else "",
            f"${row['total_assets']:,.0f}" if row['total_assets'] else "",
            row['ein']
        ])

foundations_count = cur.execute('SELECT COUNT(*) FROM foundations').fetchone()[0]
print(f"  Exported {foundations_count} foundations")

# 2. Export Centers of Influence
print("Exporting centers of influence...")
cur.execute('''
    SELECT c.id, c.name, c.title, c.role, c.employer, c.linkedin_url,
           c.phone, c.email, c.employer_address, c.employer_city, c.employer_state,
           f.name as foundation_name
    FROM centers_of_influence c
    LEFT JOIN foundations f ON c.foundation_id = f.id
    ORDER BY f.investment_assets DESC, c.role, c.name
''')

with open('exports/centers_of_influence.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['COI ID', 'Name', 'Title', 'Role', 'Employer', 'LinkedIn URL',
                     'Phone', 'Email', 'Company Address', 'Company City', 'Company State',
                     'Foundation Name'])
    for row in cur.fetchall():
        writer.writerow([
            row['id'], row['name'], row['title'], row['role'], row['employer'] or "",
            row['linkedin_url'] or "", row['phone'] or "", row['email'] or "",
            row['employer_address'] or "", row['employer_city'] or "",
            row['employer_state'] or "", row['foundation_name'] or ""
        ])

coi_count = cur.execute('SELECT COUNT(*) FROM centers_of_influence').fetchone()[0]
print(f"  Exported {coi_count} centers of influence")

# 3. Export Consultants
print("Exporting consultants...")
cur.execute('''
    SELECT c.id, c.name, c.service_type, c.amount_paid, c.assets_under_management,
           c.fee_percentage, c.description, f.name as foundation_name
    FROM consultants_990 c
    LEFT JOIN foundations f ON c.foundation_id = f.id
    WHERE c.name IS NOT NULL
    ORDER BY f.investment_assets DESC, c.assets_under_management DESC
''')

with open('exports/consultants.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Consultant ID', 'Name', 'Service Type', 'Amount Paid', 'AUM', 'Fee %', 'Description', 'Foundation'])
    for row in cur.fetchall():
        writer.writerow([
            row['id'], row['name'], row['service_type'] or "",
            f"${row['amount_paid']:,.0f}" if row['amount_paid'] else "",
            f"${row['assets_under_management']:,.0f}" if row['assets_under_management'] else "",
            f"{row['fee_percentage']*100:.1f}%" if row['fee_percentage'] else "",
            row['description'] or "", row['foundation_name'] or ""
        ])

consultants_count = cur.execute('SELECT COUNT(*) FROM consultants_990 WHERE name IS NOT NULL').fetchone()[0]
print(f"  Exported {consultants_count} consultants")

# 4. Export Priority Targets (Top 20 by assets)
print("Exporting priority targets...")
cur.execute('''
    SELECT f.id, f.name, f.city, f.investment_assets, f.email, f.website,
           f.annual_grants, c.name as coi_name, c.role as coi_role, c.employer as coi_employer
    FROM foundations f
    LEFT JOIN centers_of_influence c ON c.foundation_id = f.id 
        AND c.role IN ('Board Chair', 'CEO', 'CFO', 'President')
    WHERE f.investment_assets >= 10000000
    ORDER BY f.investment_assets DESC
    LIMIT 20
''')

with open('exports/priority_targets.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Foundation', 'City', 'Assets', 'Email', 'Website', 'Annual Grants',
                     'Key Contact', 'Contact Role', 'Contact Employer'])
    for row in cur.fetchall():
        writer.writerow([
            row['name'], row['city'], f"${row['investment_assets']:,.0f}",
            row['email'] or "", row['website'] or "",
            f"${row['annual_grants']:,.0f}" if row['annual_grants'] else "",
            row['coi_name'] or "", row['coi_role'] or "", row['coi_employer'] or ""
        ])

print(f"  Exported 20 priority targets")

# 5. Export Personnel with LinkedIn
print("Exporting personnel with LinkedIn...")
cur.execute('''
    SELECT p.id, p.name, p.title, p.employer, p.linkedin_url,
           p.is_president, p.is_ceo, p.is_cfo, p.is_treasurer, p.is_chair,
           f.name as foundation_name
    FROM personnel_990 p
    LEFT JOIN foundations f ON p.foundation_id = f.id
    WHERE p.linkedin_url IS NOT NULL AND p.linkedin_url != ""
    ORDER BY f.investment_assets DESC
''')

with open('exports/personnel_with_linkedin.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Personnel ID', 'Name', 'Title', 'Employer', 'LinkedIn URL',
                     'Is President', 'Is CEO', 'Is CFO', 'Is Treasurer', 'Is Chair', 'Foundation'])
    for row in cur.fetchall():
        writer.writerow([
            row['id'], row['name'], row['title'] or "", row['employer'] or "",
            row['linkedin_url'],
            row['is_president'], row['is_ceo'], row['is_cfo'],
            row['is_treasurer'], row['is_chair'], row['foundation_name'] or ""
        ])

personnel_count = cur.execute('SELECT COUNT(*) FROM personnel_990 WHERE linkedin_url IS NOT NULL AND linkedin_url != ""').fetchone()[0]
print(f"  Exported {personnel_count} personnel with LinkedIn")

conn.close()

print(f"\n=== Export Complete ===")
print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Files created in /home/dfoss/crm/exports/:")
print(f"  - foundations.csv ({foundations_count} rows)")
print(f"  - centers_of_influence.csv ({coi_count} rows)")
print(f"  - consultants.csv ({consultants_count} rows)")
print(f"  - priority_targets.csv (20 rows)")
print(f"  - personnel_with_linkedin.csv ({personnel_count} rows)")