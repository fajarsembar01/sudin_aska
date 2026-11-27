import re

with open("import_all_idempotent.sql", "r", encoding="utf-8") as f:
    content = f.read()

# Search for any ALTER TABLE dashboard_users adding a constraint or foreign key
matches = re.finditer(r"ALTER TABLE\s+(?:ONLY\s+)?\"?dashboard_users\"?.*?;", content, re.DOTALL | re.IGNORECASE)
print("Matches for ALTER TABLE dashboard_users:")
for m in matches:
    print(f"Match: {m.group(0)}")

# Search for FOREIGN KEY or REFERENCES in the file
matches_fk = re.finditer(r"ALTER TABLE\s+(?:ONLY\s+)?\"?\w+\"?\s+ADD\s+CONSTRAINT.*?;", content, re.DOTALL | re.IGNORECASE)
print("\nMatches for ADD CONSTRAINT:")
count = 0
for m in matches_fk:
    val = m.group(0)
    if "REFERENCES" in val or "FOREIGN KEY" in val:
        count += 1
        print(f"Match {count}: {val[:150]}...")
