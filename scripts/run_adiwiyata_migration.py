"""
Script to run database migration for adiwiyata posts and reactions.
This can be run directly from Python without needing psql command.

Run: python scripts/run_adiwiyata_migration.py
"""

from dashboard.db_access import get_cursor
import sys


def run_migration():
    """Execute the migration SQL."""

    migration_sql = open("migrations/add_adiwiyata_posts.sql", "r").read()

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
                  AND table_name IN ('portal_adiwiyata_posts', 'adiwiyata_post_likes')
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]
            if tables:
                print(f"✓ Tables ready: {', '.join(tables)}")
            else:
                print("⚠ Warning: Tables not found after migration!")
                sys.exit(1)

            # Check indexes
            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename IN ('portal_adiwiyata_posts', 'adiwiyata_post_likes')
                ORDER BY indexname
            """)
            indexes = [row[0] for row in cur.fetchall()]
            print(f"✓ Indexes: {', '.join(indexes)}")

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("Running adiwiyata migration...")
    print("=" * 60)
    run_migration()
    print("=" * 60)
    print("Migration complete!")
