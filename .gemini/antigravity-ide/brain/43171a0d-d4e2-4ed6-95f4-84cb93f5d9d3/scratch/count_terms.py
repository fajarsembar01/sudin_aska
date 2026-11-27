with open("import_all_idempotent.sql", "r", encoding="utf-8") as f:
    content = f.read()

print("Occurrences of 'school_id_fkey':", content.count("school_id_fkey"))
print("Occurrences of 'portal_schools':", content.count("portal_schools"))
print("Occurrences of 'REFERENCES':", content.count("REFERENCES"))
print("Occurrences of 'FOREIGN KEY':", content.count("FOREIGN KEY"))
