import os
import psycopg2
from dotenv import load_dotenv

dotenv_path = r"c:\Users\User\Documents\GitHub\sudin_aska\.env"
print(f"Loading environment from {dotenv_path}...")
load_dotenv(dotenv_path=dotenv_path)

db_name = os.getenv("DB_NAME")
db_user = os.getenv("DB_USER")
db_pass = os.getenv("DB_PASS")
db_host = os.getenv("DB_HOST", "127.0.0.1")
db_port = os.getenv("DB_PORT", "5432")

print(f"Connecting to database '{db_name}' as '{db_user}' on {db_host}:{db_port}...")
conn = psycopg2.connect(
    dbname=db_name,
    user=db_user,
    password=db_pass,
    host=db_host,
    port=db_port,
)
conn.autocommit = True

try:
    with conn.cursor() as cur:
        # Get all foreign keys
        cur.execute("""
            SELECT 
                conrelid::regclass::text AS table_name, 
                conname AS constraint_name
            FROM pg_constraint 
            WHERE contype = 'f';
        """)
        fks = cur.fetchall()
        
        print(f"Found {len(fks)} foreign key constraints to drop:")
        for tbl, constr in fks:
            print(f" - Dropping {constr} on {tbl}...")
            cur.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {constr} CASCADE;")
            
        print("All foreign key constraints dropped.")
        
        # Run the import SQL script
        sql_path = r"c:\Users\User\Documents\GitHub\sudin_aska\import_all_idempotent.sql"
        print(f"Reading SQL script from {sql_path}...")
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()
            
        print("Executing SQL script (this will take a moment)...")
        cur.execute(sql)
        print("SQL script executed successfully!")
        
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
