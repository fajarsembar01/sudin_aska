
import sys
import os
from contextlib import contextmanager
from typing import Generator, Optional

try:
    from psycopg2 import pool
    from psycopg2.extras import DictCursor
    from dotenv import load_dotenv
except ImportError:
    print("Missing required packages (psycopg2, python-dotenv).")
    sys.exit(1)

# Load env from current directory or parent
load_dotenv()
# Also try loading from param if needed, but usually .env is in project root
project_root = "/Users/ainunfajar/SUDIN_ASKA/ai-agent-sekolah"
load_dotenv(os.path.join(project_root, ".env"))

REQUIRED_KEYS = [
    "DB_NAME",
    "DB_USER",
    "DB_PASS",
    "DB_HOST",
    "DB_PORT",
]

_DB_CONFIG = {key: os.getenv(key) for key in REQUIRED_KEYS}
_missing = [key for key, value in _DB_CONFIG.items() if not value]
if _missing:
    print(f"Missing DB config: {_missing}")
    # Fallback to defaults or error?
    # sys.exit(1)

# Minimal DB setup
optional_sslmode: Optional[str] = os.getenv("DB_SSLMODE")
conn_kwargs = dict(
    dbname=_DB_CONFIG.get("DB_NAME"),
    user=_DB_CONFIG.get("DB_USER"),
    password=_DB_CONFIG.get("DB_PASS"),
    host=_DB_CONFIG.get("DB_HOST"),
    port=_DB_CONFIG.get("DB_PORT"),
)
if optional_sslmode:
    conn_kwargs["sslmode"] = optional_sslmode

try:
    _POOL = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=1,
        **conn_kwargs,
    )
except Exception as e:
    print(f"Failed to connect to DB: {e}")
    sys.exit(1)

@contextmanager
def get_cursor(commit: bool = False):
    connection = _POOL.getconn()
    try:
        cursor = connection.cursor(cursor_factory=DictCursor)
        yield cursor
        if commit:
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        _POOL.putconn(connection)

def check_score(school_name_query):
    print(f"Searching for school: {school_name_query}")
    with get_cursor() as cur:
        # Find school
        cur.execute("SELECT id, npsn, name FROM portal_schools WHERE name ILIKE %s", (f"%{school_name_query}%",))
        school = cur.fetchone()
        
        if not school:
            print("School not found.")
            return

        print(f"Found School: {school['name']} (ID: {school['id']}, NPSN: {school['npsn']})")
        school_id = school['id']

        # Check assessments
        cur.execute("""
            SELECT id, status, total_score, staff_id, submitted_at, created_at
            FROM portal_assessments 
            WHERE school_id = %s
            ORDER BY created_at DESC
        """, (school_id,))
        
        assessments = cur.fetchall()
        print(f"\nFound {len(assessments)} assessments:")
        for a in assessments:
            print(f" - ID: {a['id']}, Status: {a['status']}, Total Score: {a['total_score']}, Date: {a['submitted_at'] or a['created_at']}")

        # Check details for latest submitted assessment
        submitted = [a for a in assessments if a['status'] == 'submitted']
        if submitted:
            latest_id = submitted[0]['id']
            print(f"\nChecking scores for Assessment ID: {latest_id}")
            
            # Check individual scores
            cur.execute("""
                SELECT s.score, r.name as room_name, a.name as aspect_name
                FROM portal_assessment_scores s
                JOIN portal_school_rooms sr ON s.school_room_id = sr.id
                JOIN portal_rooms r ON sr.room_id = r.id
                JOIN portal_aspects a ON s.aspect_id = a.id
                WHERE s.assessment_id = %s
            """, (latest_id,))
            scores = cur.fetchall()
            
            count = len(scores)
            total = sum(s['score'] for s in scores)
            avg = total / count if count else 0
            
            print(f" - Count of scores: {count}")
            print(f" - Sum of scores: {total}")
            print(f" - Calculated Average: {avg:.2f}")
            print(f" - Stored Total Score: {submitted[0]['total_score']}")
            
            if not scores:
                print(" -> No scores found in portal_assessment_scores table!")
        else:
            print("\nNo submitted assessments found.")

if __name__ == "__main__":
    check_score("MIN 20 JAKARTA")
