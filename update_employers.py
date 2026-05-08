import sqlite3
import json

# Load all result batches
all_results = []
for b in range(1, 5):
    with open(f'employer_batch_{b}_results.json') as f:
        results = json.load(f)
        all_results.extend(results)
    print(f'Loaded {len(results)} from batch {b}')

print(f'\nTotal results: {len(all_results)}')

# Update database
conn = sqlite3.connect('database/louisiana_foundations.db')
cur = conn.cursor()

updated = 0
skipped = 0
not_found = 0

for r in all_results:
    employer = r.get('employer')
    if employer:
        cur.execute('UPDATE personnel_990 SET employer = ? WHERE id = ?', (employer, r['id']))
        updated += 1
        print(f'Updated ID {r["id"]}: {r["name"]} -> {employer}')
    else:
        not_found += 1
        print(f'No employer found: {r["name"]}')

conn.commit()

# Verify
cur.execute('SELECT COUNT(*) FROM personnel_990 WHERE employer IS NOT NULL AND employer != ""')
total_with_employer = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM personnel_990')
total_records = cur.fetchone()[0]

print(f'\n=== SUMMARY ===')
print(f'Updated {updated} records with employer data')
print(f'{not_found} records had no employer found')
print(f'Total with employer: {total_with_employer}/{total_records} ({100*total_with_employer/total_records:.1f}%)')

conn.close()
