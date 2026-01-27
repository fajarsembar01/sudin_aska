from dashboard.app import create_app
from dashboard.db_access import get_cursor

app = create_app()
with app.app_context():
    try:
        with get_cursor() as cur:
            print("--- Assessment Status Counts ---")
            cur.execute("SELECT status, count(*) FROM portal_assessments GROUP BY status")
            rows = cur.fetchall()
            if not rows:
                print("No assessments found.")
            else:
                for row in rows:
                    print(row)
            
            print("\n--- Recent Assessments Query Check ---")
            cur.execute("""
                SELECT 
                    a.id, a.school_id, s.name as school_name, a.status, a.total_score, a.created_by, u.full_name
                FROM portal_assessments a
                JOIN portal_schools s ON a.school_id = s.id
                LEFT JOIN web_users u ON a.created_by = u.email
                ORDER BY a.submitted_at DESC
                LIMIT 5
            """)
            recents = cur.fetchall()
            for r in recents:
                print(r)
                
    except Exception as e:
        print(f"Error: {e}")
