"""
Script to run database migration for kecamatan access control.
This can be run directly from Python without needing psql command.
"""

from dashboard.db_access import get_cursor
import sys


def run_migration():
    """Execute the migration SQL."""
    
    migration_sql = open("migrations/add_kecamatan_access.sql", "r").read()
    
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(migration_sql)
            print("✓ Migration completed successfully!")
            print("\nVerifying migration...")
            
            # Verify tables exist
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                  AND table_name IN ('user_kecamatan', 'staff_school_assignments', 'school_classrooms')
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]
            print(f"✓ Created tables: {', '.join(tables)}")
            
            # Check admin assignments
            cur.execute("""
                SELECT COUNT(*) as admin_count
                FROM dashboard_users WHERE role = 'admin'
            """)
            admin_count = cur.fetchone()[0]
            
            cur.execute("""
                SELECT COUNT(DISTINCT user_id) as assigned_admins
                FROM user_kecamatan
            """)
            assigned_count = cur.fetchone()[0]
            
            print(f"✓ Total admin users: {admin_count}")
            print(f"✓ Admins with kecamatan access: {assigned_count}")
            
            if admin_count == assigned_count:
                print("✓ All admins have been assigned to all kecamatans!")
            else:
                print(f"⚠ Warning: {admin_count - assigned_count} admins without kecamatan access")
            
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("Running database migration for kecamatan access control...")
    print("=" * 60)
    run_migration()
    print("=" * 60)
    print("Migration process complete!")
