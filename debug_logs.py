from dashboard.db_access import get_cursor

def check_logs():
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM portal_activity_logs")
        count = cur.fetchone()[0]
        print(f"Total log records: {count}")
        
        if count > 0:
            cur.execute("SELECT * FROM portal_activity_logs ORDER BY created_at DESC LIMIT 5")
            logs = cur.fetchall()
            print("Latest logs:")
            for log in logs:
                print(log)

if __name__ == "__main__":
    check_logs()
