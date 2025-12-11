import os
import sys

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dashboard.db_access import get_cursor
from dashboard.schema import _PORTAL_ASSESSMENT_PERIODS_SQL, _PORTAL_ASSESSMENT_PERIODS_INDEX_SQL

def migrate():
    print("Running migration...")
    
    with get_cursor(commit=True) as cur:
        # 1. Create Table manually to be sure
        print("Creating table portal_assessment_periods...")
        try:
            cur.execute(_PORTAL_ASSESSMENT_PERIODS_SQL)
            cur.execute(_PORTAL_ASSESSMENT_PERIODS_INDEX_SQL)
        except Exception as e:
            print(f"Table creation warning (might exist): {e}")
        
        # 2. Add column to portal_assessments
        print("Adding period_id to portal_assessments...")
        try:
            cur.execute("ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS period_id INTEGER REFERENCES portal_assessment_periods(id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_portal_assessments_period ON portal_assessments (period_id)")
        except Exception as e:
             # Ignore if exists (IF NOT EXISTS should handle it but logging is good)
             print(f"Column addition warning: {e}")

        # 3. Create Period "Semester 2 2025"
        print("Creating Period: Semester 2 2025...")
        cur.execute("""
            INSERT INTO portal_assessment_periods (name, start_date, end_date, is_active)
            VALUES ('Semester 2 2025', '2025-01-01', '2025-06-30', TRUE)
            ON CONFLICT DO NOTHING
            RETURNING id
        """)
        row = cur.fetchone()
        
        if not row:
            # If inserted nothing, maybe it exists?
            cur.execute("SELECT id FROM portal_assessment_periods WHERE name = 'Semester 2 2025'")
            row = cur.fetchone()
        
        period_id = row['id']
        print(f"Period ID: {period_id}")

        # 4. Update existing submitted/verified assessments
        print("Updating existing assessments...")
        cur.execute("""
            UPDATE portal_assessments 
            SET period_id = %s 
            WHERE status IN ('submitted', 'verified') 
            AND period_id IS NULL
        """, (period_id,))
        
        count = cur.rowcount
        print(f"Updated {count} assessments to use period {period_id}.")
        
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
