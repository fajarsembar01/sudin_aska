with open("import_all_idempotent.sql", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Searching for 'portal_schools' inserts...")
for i, line in enumerate(lines):
    if "INSERT INTO" in line and "portal_schools" in line:
        print(f"Line {i+1}: {line[:150]}")

print("\nSearching for '704'...")
for i, line in enumerate(lines):
    if "704" in line:
        print(f"Line {i+1}: {line[:150]}")
