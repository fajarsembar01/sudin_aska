import os
import re
import psycopg2
import subprocess
from dotenv import load_dotenv

# Load env
dotenv_path = r"c:\Users\User\Documents\GitHub\sudin_aska\.env"
print(f"Loading environment from {dotenv_path}...")
load_dotenv(dotenv_path=dotenv_path)

db_name = os.getenv("DB_NAME")
db_user = os.getenv("DB_USER")
db_pass = os.getenv("DB_PASS")
db_host = os.getenv("DB_HOST", "127.0.0.1")
db_port = os.getenv("DB_PORT", "5432")

# 1. Reset database
print(f"Connecting to database '{db_name}' to reset public schema...")
conn = psycopg2.connect(
    dbname=db_name,
    user=db_user,
    password=db_pass,
    host=db_host,
    port=db_port,
)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
print("Schema public reset.")

# 2. Extract sequences and create them
sql_path = r"c:\Users\User\Documents\GitHub\sudin_aska\import_all_idempotent.sql"
print(f"Reading SQL script from {sql_path} to detect sequences...")
with open(sql_path, "r", encoding="utf-8") as f:
    sql = f.read()

# Find nextval('sequence_name')
seq_pattern = re.compile(r"nextval\('(\w+)'", re.IGNORECASE)
sequences = sorted(list(set(seq_pattern.findall(sql))))

print(f"Creating {len(sequences)} sequences...")
with conn.cursor() as cur:
    for seq in sequences:
        cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq};")
print("All sequences created successfully.")

# Helper to split SQL by statement
def split_sql(sql_text):
    statements = []
    current = []
    in_quote = False
    in_dollar = False
    
    i = 0
    n = len(sql_text)
    while i < n:
        char = sql_text[i]
        
        if char == '$' and i + 1 < n and sql_text[i+1] == '$':
            in_dollar = not in_dollar
            current.append('$$')
            i += 2
            continue
            
        if not in_dollar:
            if char == "'":
                if i > 0 and sql_text[i-1] == '\\':
                    pass
                else:
                    in_quote = not in_quote
                
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

print("Parsing SQL statements...")
statements = split_sql(sql)
print(f"Parsed {len(statements)} statements.")

# Categorize and clean REFERENCES
ref_pattern = re.compile(
    r'REFERENCES\s+("?\w+"?)\s*(\(\s*"?(?:\w+)"?\s*\))?(?:\s+ON\s+DELETE\s+[A-Z\s_]+)?(?:\s+ON\s+UPDATE\s+[A-Z\s_]+)?',
    re.IGNORECASE
)

setup_stmts = []
create_stmts = []
alter_stmts = []
insert_stmts = []
other_stmts = []

for stmt in statements:
    clean = re.sub(r'--.*$', '', stmt, flags=re.MULTILINE).strip()
    if not clean:
        continue
    
    cleaned_stmt = ref_pattern.sub("", stmt)
    
    upper = clean.upper()
    if upper.startswith("SET ") or upper.startswith("SHOW "):
        setup_stmts.append(cleaned_stmt)
    elif upper.startswith("CREATE TABLE"):
        create_stmts.append(cleaned_stmt)
    elif upper.startswith("ALTER TABLE"):
        alter_stmts.append(cleaned_stmt)
    elif upper.startswith("INSERT INTO"):
        insert_stmts.append(cleaned_stmt)
    elif upper in ("BEGIN;", "COMMIT;", "ROLLBACK;"):
        continue
    else:
        other_stmts.append(cleaned_stmt)

def execute_batch(cur, title, stmts, log_all_errors=False):
    print(f"Executing {title} ({len(stmts)} statements)...")
    success_count = 0
    fail_count = 0
    for stmt in stmts:
        try:
            cur.execute(stmt)
            success_count += 1
        except Exception as e:
            fail_count += 1
            err_msg = str(e)
            if log_all_errors or ("already exists" not in err_msg and "duplicate" not in err_msg):
                stmt_preview = stmt.replace('\n', ' ')[:80]
                print(f"Warning: stmt [{stmt_preview}...] failed: {err_msg.strip()}")
    print(f"Finished {title}: {success_count} succeeded, {fail_count} failed/skipped.")

# 3. Execute in correct order
with conn.cursor() as cur:
    execute_batch(cur, "setup statements", setup_stmts)
    execute_batch(cur, "CREATE TABLE statements", create_stmts)
    execute_batch(cur, "ALTER TABLE statements", alter_stmts, log_all_errors=True)
    execute_batch(cur, "INSERT INTO statements", insert_stmts)
    execute_batch(cur, "other statements", other_stmts)

print("Database data successfully loaded!")
conn.close()

# 4. Run app initialization in the correct circular-dependency-safe order: dashboard first, then db
print("Running app CLI schema initializations to re-add constraints...")
try:
    print("Running dashboard schema init first...")
    subprocess.run([r".\venv\Scripts\python.exe", "-m", "dashboard.cli", "init-db"], check=True)
    print("Running core db schema init second...")
    subprocess.run([r".\venv\Scripts\python.exe", "db.py"], check=True)
    print("All constraints successfully restored!")
except Exception as e:
    print(f"Error during schema initialization: {e}")
