
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

def verify_schema():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )
    cursor = conn.cursor()

    # List of expected tables
    expected_tables = [
        "chat_logs", "bullying_reports", "psych_reports", "chat_feedback", "web_users", "telegram_users",
        "dashboard_users", "school_classes", "students", "notifications", "twitter_worker_logs",
        "portal_schools", "portal_rooms", "portal_aspects", "portal_school_rooms",
        "portal_assessment_periods", "portal_assessments", "portal_assessment_scores",
        "portal_assessment_photos", "portal_assessment_room_details"
    ]

    print("Checking tables...")
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
    """)
    existing_tables = set(row[0] for row in cursor.fetchall())
    
    missing = []
    for t in expected_tables:
        if t in existing_tables:
            print(f"  [OK] {t}")
        else:
            print(f"  [MISSING] {t}")
            missing.append(t)

    print("\nChecking foreign keys for portal_aspects...")
    cursor.execute("""
        SELECT
            tc.constraint_name, 
            kcu.column_name, 
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name 
        FROM 
            information_schema.table_constraints AS tc 
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name='portal_aspects';
    """)
    fks = cursor.fetchall()
    if fks:
        for fk in fks:
            print(f"  [OK] FK found: {fk}")
    else:
        print("  [WARNING] No Foreign Keys found for portal_aspects!")

    print("\nChecking foreign keys for portal_assessments...")
    cursor.execute("""
        SELECT
            kcu.column_name, 
            ccu.table_name AS foreign_table_name
        FROM 
            information_schema.table_constraints AS tc 
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name='portal_assessments';
    """)
    fks = cursor.fetchall()
    for fk in fks:
        print(f"  [OK] FK: {fk[0]} -> {fk[1]}")

    conn.close()

if __name__ == "__main__":
    verify_schema()
