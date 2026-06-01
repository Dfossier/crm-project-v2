import json

with open('employer_search_batch.json') as f:
    data = json.load(f)

batch_size = (len(data) + 3) // 4

for i in range(4):
    batch = data[i*batch_size:(i+1)*batch_size]
    with open(f'employer_batch_{i+1}.json', 'w') as f:
        json.dump(batch, f, indent=2)
    print(f'Batch {i+1}: {len(batch)} members')

print(f'Total: {len(data)} members split into 4 batches')
