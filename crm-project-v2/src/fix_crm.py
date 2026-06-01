import re

with open('/home/dfoss/crm/src/crm_app.py', 'r') as f:
    content = f.read()

# Fix 1: Replace bare except with except Exception
content = re.sub(r'except\s*:', 'except Exception:', content)

# Fix 2: Replace iterrows() with itertuples(index=False)
content = content.replace('.iterrows()', '.itertuples(index=False)')

# Fix 3: Replace row['field'] with row.field for itertuples compatibility
replacements = [
    ("row['name']", "row.name"),
    ("row['foundation_name']", "row.foundation_name"),
    ("row['city']", "row.city"),
    ("row['contact_person']", "row.contact_person"),
    ("row['interaction_type']", "row.interaction_type"),
    ("row['foundation_city']", "row.foundation_city"),
    ("row['follow_up_date']", "row.follow_up_date"),
    ("row['subject']", "row.subject"),
    ("row['notes']", "row.notes"),
    ("row['website']", "row.website"),
    ("row['days_until_due']", "row.days_until_due"),
    ("row['id']", "row.id"),
    ("row['ein']", "row.ein"),
]

for old, new in replacements:
    content = content.replace(old, new)

# Fix 4: Add SQL injection whitelist protection
content = content.replace(
    "tables = ['foundations', 'personnel', 'focus_areas', 'grants', 'interactions']",
    "ALLOWED_TABLES = {'foundations', 'personnel', 'focus_areas', 'grants', 'interactions'}\n                tables = ['foundations', 'personnel', 'focus_areas', 'grants', 'interactions']"
)

content = content.replace(
    "for table in tables:\n                    count = pd.read_sql_query",
    "for table in tables:\n                    if table not in ALLOWED_TABLES:\n                        continue\n                    count = pd.read_sql_query"
)

with open('/home/dfoss/crm/src/crm_app.py', 'w') as f:
    f.write(content)

print("Fixes applied successfully")
