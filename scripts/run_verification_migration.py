"""
Script to run database migration for user verification.
"""

import sys

from dashboard.db_access import get_cursor


def run_migration():
    """Execute the migration SQL."""

    try:
        # Read the SQL file
        migration_sql = open("migrations/add_user_verification.sql", "r").read()

        with get_cursor(commit=True) as cur:
            cur.execute(migration_sql)
            print("✓ Migration completed successfully!")

            # Verify columns exist
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'dashboard_users' 
                  AND column_name IN ('whatsapp_number', 'account_status', 'requested_kecamatan')
            """)
            columns = [row[0] for row in cur.fetchall()]
            print(f"✓ Verified columns: {', '.join(columns)}")

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("Running database migration for user verification...")
    run_migration()
