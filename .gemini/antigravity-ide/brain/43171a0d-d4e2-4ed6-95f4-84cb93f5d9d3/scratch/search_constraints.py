with open("import_all_idempotent.sql", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Searching for constraints on dashboard_users...")
for i, line in enumerate(lines):
    if "dashboard_users" in line and "CONSTRAINT" in line:
        print(f"Line {i+1}: {line.strip()[:150]}")
    if "dashboard_users" in line and "FOREIGN KEY" in line:
        print(f"Line {i+1}: {line.strip()[:150]}")
