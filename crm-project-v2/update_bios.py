import sqlite3
import json

# Load all result batches
all_results = []
for b in range(1, 5):
    try:
        with open(f'foundation_bio_batch_{b}_results.json') as f:
            results = json.load(f)
            all_results.extend(results)
            print(f'Loaded {len(results)} from batch {b}')
    except FileNotFoundError:
        print(f'Batch {b} file not found')

print(f'\nTotal biographical entries: {len(all_results)}')

# Update database
conn = sqlite3.connect('database/louisiana_foundations.db')
cur = conn.cursor()

updated = 0
skipped = 0

for r in all_results:
    bio = r.get('biography')
    if bio and len(bio) > 20:  # Only update if there's meaningful content
        cur.execute('UPDATE personnel_990 SET biography = ? WHERE id = ?', (bio, r['personnel_id']))
        updated += 1
        print(f'Updated ID {r["personnel_id"]}: {r["name"][:40]}...')
    else:
        skipped += 1

conn.commit()

# Verify
cur.execute('SELECT COUNT(*) FROM personnel_990 WHERE biography IS NOT NULL AND biography != ""')
total_with_bio = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM personnel_990')
total_records = cur.fetchone()[0]

print(f'\n=== SUMMARY ===')
print(f'Updated {updated} records with biographical data')
print(f'{skipped} entries skipped (empty or too short)')
print(f'Total with biography: {total_with_bio}/{total_records} ({100*total_with_bio/total_records:.1f}%)')

conn.close()
