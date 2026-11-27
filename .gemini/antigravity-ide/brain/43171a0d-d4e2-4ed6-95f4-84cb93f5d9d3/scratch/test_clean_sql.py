import re

# Read the file
sql_path = "import_all_idempotent.sql"
with open(sql_path, "r", encoding="utf-8") as f:
    sql = f.read()

# Define regex to match REFERENCES clause
# Example: REFERENCES "dashboard_users"("id") ON DELETE CASCADE
ref_pattern = re.compile(
    r'REFERENCES\s+("?\w+"?)\s*(\(\s*"?(?:\w+)"?\s*\))?(?:\s+ON\s+DELETE\s+[A-Z\s_]+)?(?:\s+ON\s+UPDATE\s+[A-Z\s_]+)?',
    re.IGNORECASE
)

cleaned_sql = ref_pattern.sub("", sql)

# Print occurrences before and after
print("Before cleaning:")
print(" REFERENCES count:", sql.lower().count("references"))
print("After cleaning:")
print(" REFERENCES count:", cleaned_sql.lower().count("references"))

# Write the cleaned SQL to a test file
with open("import_cleaned_temp.sql", "w", encoding="utf-8") as f:
    f.write(cleaned_sql)
print("Saved to import_cleaned_temp.sql")
