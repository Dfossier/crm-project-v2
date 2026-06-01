import sqlite3
import json

conn = sqlite3.connect('database/louisiana_foundations.db')
cur = conn.cursor()

# Get foundations with websites
cur.execute('''
    SELECT f.id, f.name, f.website, 
           GROUP_CONCAT(p.name || "|" || p.id, ",")
    FROM foundations f
    LEFT JOIN personnel_990 p ON f.id = p.foundation_id
    WHERE f.website IS NOT NULL AND f.website != ""
    GROUP BY f.id
    ORDER BY f.name
''')

foundations = cur.fetchall()
print(f'Found {len(foundations)} foundations with websites\n')

# Create batches for parallel processing
batch_size = 10
batches = []
for i in range(0, len(foundations), batch_size):
    batch = []
    for f in foundations[i:i+batch_size]:
        personnel_list = []
        if f[3]:
            for item in f[3].split(','):
                parts = item.split('|')
                personnel_list.append({'id': int(parts[1]), 'name': parts[0]})
        batch.append({
            'foundation_id': f[0],
            'foundation_name': f[1],
            'website': f[2],
            'personnel': personnel_list
        })
    batches.append(batch)

for i, batch in enumerate(batches):
    with open(f'foundation_bio_batch_{i+1}.json', 'w') as f:
        json.dump(batch, f, indent=2)
    print(f'Batch {i+1}: {len(batch)} foundations')

conn.close()
print(f'\nTotal: {len(foundations)} foundations split into {len(batches)} batches')
