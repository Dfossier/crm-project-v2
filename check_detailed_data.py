#!/usr/bin/env python3

import sqlite3
conn = sqlite3.connect('database/louisiana_foundations.db')
cursor = conn.cursor()

print('📊 CURRENT DETAILED DATA STATUS:')

cursor.execute('SELECT COUNT(*) FROM personnel_990')
personnel_count = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM consultants_990')
consultant_count = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM investment_details')
investment_count = cursor.fetchone()[0]

print(f'   👥 Personnel records: {personnel_count}')
print(f'   💼 Consultant records: {consultant_count}')
print(f'   📊 Investment records: {investment_count}')

if personnel_count > 0:
    print()
    print('💰 TOP EXECUTIVE COMPENSATION:')
    cursor.execute('''
        SELECT f.name, p.name, p.title, p.compensation, p.benefits
        FROM personnel_990 p
        JOIN foundations f ON p.foundation_id = f.id
        WHERE (p.is_president = 1 OR p.is_ceo = 1) AND p.compensation > 0
        ORDER BY p.compensation DESC
        LIMIT 10
    ''')
    
    for fname, pname, title, comp, benefits in cursor.fetchall():
        total_comp = comp + (benefits or 0)
        print(f'   • {pname} ({title})')
        print(f'     {fname} | ${comp:,} base + ${benefits or 0:,} benefits = ${total_comp:,}')

if consultant_count > 0:
    print()
    print('💼 TOP INVESTMENT MANAGEMENT FEES:')
    cursor.execute('''
        SELECT f.name, c.name, c.amount_paid, c.fee_percentage
        FROM consultants_990 c
        JOIN foundations f ON c.foundation_id = f.id
        WHERE c.is_investment_advisor = 1
        ORDER BY c.amount_paid DESC
        LIMIT 10
    ''')
    
    total_fees = 0
    for fname, cname, amount, fee_pct in cursor.fetchall():
        total_fees += amount or 0
        fee_str = f'({fee_pct*100:.2f}%)' if fee_pct else ''
        print(f'   • {cname}')
        print(f'     Managing {fname} | ${amount:,.0f}/year {fee_str}')
    
    print('')
    print(f'📊 Total annual investment management fees: ${total_fees:,.0f}')

conn.close()