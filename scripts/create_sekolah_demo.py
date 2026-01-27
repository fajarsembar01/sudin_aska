import os
import psycopg2
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

# Load env vars
load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

def get_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )


def create_sekolah_demo():
    email = "sekolah_demo@test.com"
    password = "password123"
    full_name = "Sekolah Demo Account"
    role = "sekolah"
    
    print(f"Connecting to DB {DB_NAME} at {DB_HOST}...")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            print(f"Checking if {email} exists...")
            cur.execute("SELECT id FROM dashboard_users WHERE email = %s", (email,))
            existing = cur.fetchone()
            
            if existing:
                print(f"User {email} already exists (ID: {existing[0]}). Updating password...")
                ph = generate_password_hash(password, method="pbkdf2:sha256", salt_length=12)
                cur.execute("UPDATE dashboard_users SET password_hash = %s WHERE id = %s", (ph, existing[0]))
                print("Password key updated.")
            else:
                print(f"Creating user {email}...")
                ph = generate_password_hash(password, method="pbkdf2:sha256", salt_length=12)
                cur.execute(
                    """
                    INSERT INTO dashboard_users (email, full_name, password_hash, role, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    RETURNING id
                    """,
                    (email, full_name, ph, role)
                )
                new_id = cur.fetchone()[0]
                print(f"User created successfully with ID: {new_id}")
            
            conn.commit()
            print("Transaction Committed.")
            
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    create_sekolah_demo()
