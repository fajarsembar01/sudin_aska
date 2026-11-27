import re

def split_sql(sql_text):
    statements = []
    current = []
    in_quote = False
    in_dollar = False
    
    i = 0
    n = len(sql_text)
    while i < n:
        char = sql_text[i]
        
        # Handle dollar quoting $$
        if char == '$' and i + 1 < n and sql_text[i+1] == '$':
            in_dollar = not in_dollar
            current.append('$$')
            i += 2
            continue
            
        if not in_dollar:
            # Handle standard single quotes
            if char == "'":
                # Check for escaped quotes (simple backslash check)
                if i > 0 and sql_text[i-1] == '\\':
                    pass
                else:
                    in_quote = not in_quote
                
            # Handle semicolon
            if char == ';' and not in_quote:
                current.append(';')
                statements.append("".join(current).strip())
                current = []
                i += 1
                continue
                
        current.append(char)
        i += 1
        
    if current:
        remaining = "".join(current).strip()
        if remaining:
            statements.append(remaining)
            
    return statements

# Read the file
sql_path = "import_all_idempotent.sql"
with open(sql_path, "r", encoding="utf-8") as f:
    content = f.read()

print("Splitting SQL into statements...")
statements = split_sql(content)
print(f"Total statements found: {len(statements)}")

create_tables = []
alter_tables = []
inserts = []
others = []

for stmt in statements:
    # Clean comment lines
    clean = re.sub(r'--.*$', '', stmt, flags=re.MULTILINE).strip()
    if not clean:
        continue
        
    upper = clean.upper()
    if upper.startswith("CREATE TABLE"):
        create_tables.append(stmt)
    elif upper.startswith("ALTER TABLE"):
        alter_tables.append(stmt)
    elif upper.startswith("INSERT INTO"):
        inserts.append(stmt)
    else:
        others.append(stmt)

print(f"CREATE TABLE statements: {len(create_tables)}")
print(f"ALTER TABLE statements: {len(alter_tables)}")
print(f"INSERT INTO statements: {len(inserts)}")
print(f"Other statements: {len(others)}")

# Print a few samples of other statements
print("\nSample of other statements:")
for i, stmt in enumerate(others[:5]):
    print(f" - {i+1}: {stmt[:100]}...")
