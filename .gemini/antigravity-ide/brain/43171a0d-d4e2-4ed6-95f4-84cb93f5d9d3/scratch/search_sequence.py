with open("import_all_idempotent.sql", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "SEQUENCE" in line.upper():
        print(f"Line {i+1}: {line.strip()[:180]}")
