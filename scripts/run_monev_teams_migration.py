"""
Script to run monev teams migration.
"""
from dashboard.db_access import get_cursor
import sys

def run_migration():
    """Execute the migration SQL."""
    
    try:
        # Read the SQL file
        migration_sql = open("migrations/create_monev_teams.sql", "r").read()
        
        with get_cursor(commit=True) as cur:
            cur.execute(migration_sql)
            print("✓ Migration completed successfully!")
            
            # Verify tables exist
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name IN ('monev_teams', 'monev_team_members')
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]
            print(f"✓ Created tables: {', '.join(tables)}")
            
            # Count teams
            cur.execute("SELECT COUNT(*) FROM monev_teams")
            team_count = cur.fetchone()[0]
            print(f"✓ Initialized {team_count} monev team(s)")
            
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    print("Running monev teams migration...")
    print("=" * 60)
    run_migration()
    print("=" * 60)
    print("Migration complete!")
