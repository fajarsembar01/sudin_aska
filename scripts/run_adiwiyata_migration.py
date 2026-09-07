"""
Script to run database migration for adiwiyata posts and reactions.
Standalone — tidak perlu import dashboard, langsung baca .env

Run: python3 scripts/run_adiwiyata_migration.py
"""

import os
import sys
from contextlib import contextmanager


# Load .env dari root project
def load_env(env_path=".env"):
    if not os.path.exists(env_path):
        print(f"⚠ .env file not found at {env_path}")
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


load_env()

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("✗ psycopg2 tidak ter-install. Jalankan: pip install psycopg2-binary")
    sys.exit(1)


def get_conn():
    host = os.getenv("DB_HOST", "127.0.0.1")
    if host.lower() == "localhost":
        host = "127.0.0.1"
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=host,
        port=os.getenv("DB_PORT", "5432"),
        options="-c timezone=Asia/Jakarta",
    )


def run_migration():
    """Execute the migration SQL."""
    migration_file = "migrations/add_adiwiyata_posts.sql"
    if not os.path.exists(migration_file):
        print(f"✗ File tidak ditemukan: {migration_file}")
        sys.exit(1)

    migration_sql = open(migration_file).read()

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(migration_sql)
        conn.commit()
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

        cur.close()
        conn.close()

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
