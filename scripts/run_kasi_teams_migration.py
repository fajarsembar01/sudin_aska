"""
Migration script to add Kasi teams support.
Run: python3 run_kasi_teams_migration.py
"""

import os

import psycopg2
from dotenv import load_dotenv

# Load from .env
load_dotenv()

# Get DB credentials from environment (same as db.py)
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_SSLMODE = os.getenv("DB_SSLMODE")


def run_migration():
    print("🚀 Running Kasi Teams Migration...")

    # Build connection args
    conn_args = dict(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
    )
    if DB_SSLMODE:
        conn_args["sslmode"] = DB_SSLMODE

    conn = psycopg2.connect(**conn_args)
    cur = conn.cursor()

    try:
        # Step 1: Add team_type column
        print("  Adding team_type column...")
        cur.execute(
            "ALTER TABLE monev_teams ADD COLUMN IF NOT EXISTS team_type VARCHAR(20) DEFAULT 'kecamatan'"
        )

        # Step 2: Drop NOT NULL constraint on kecamatan_id (Kasi teams don't have kecamatan)
        print("  Allowing NULL kecamatan_id for Kasi teams...")
        cur.execute("ALTER TABLE monev_teams ALTER COLUMN kecamatan_id DROP NOT NULL")

        # Step 3: Drop NOT NULL constraint on name column
        print("  Allowing NULL name for flexibility...")
        cur.execute("ALTER TABLE monev_teams ALTER COLUMN name DROP NOT NULL")

        # Step 4: Update existing teams with team_type = kecamatan
        print("  Updating existing kecamatan teams...")
        cur.execute(
            "UPDATE monev_teams SET team_type = 'kecamatan' WHERE kecamatan_id IS NOT NULL"
        )

        # Step 5: Create Kasi teams
        print("  Creating Kasi teams...")
        kasi_teams = [
            "PAUD PMPK",
            "SD",
            "SMP SMA",
            "SMK, Kursus & Pelatihan",
        ]
        for team_name in kasi_teams:
            cur.execute(
                """INSERT INTO monev_teams (kecamatan_id, name, team_type, coordinator_id, created_at, updated_at) 
                   VALUES (NULL, %s, 'kasi', NULL, NOW(), NOW()) 
                   ON CONFLICT DO NOTHING""",
                (team_name,),
            )

        conn.commit()
        print("✅ Migration completed successfully!")

        # Verify results
        cur.execute(
            "SELECT id, team_type, name, kecamatan_id FROM monev_teams ORDER BY team_type, id"
        )
        teams = cur.fetchall()

        print("\n📋 Current Teams:")
        print("-" * 60)
        for team in teams:
            team_id, team_type, name, kec_id = team
            display_name = name if name else f"Kecamatan ID: {kec_id}"
            print(f"  [{team_type}] {display_name} (ID: {team_id})")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    run_migration()
