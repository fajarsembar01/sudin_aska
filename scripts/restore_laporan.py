import os
import sys
import subprocess

# Add project root to path to import db modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from dashboard.db_access import get_cursor, shutdown_pool

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/restore_laporan.py <path_to_backup_file>")
        sys.exit(1)
        
    backup_file = sys.argv[1]
    if not os.path.exists(backup_file):
        print(f"Error: Backup file '{backup_file}' not found.")
        sys.exit(1)
        
    print("1. Menghapus tabel laporan lama (cascade drop)...")
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("DROP TABLE IF EXISTS laporan_submission_files CASCADE;")
            cur.execute("DROP TABLE IF EXISTS laporan_submission_answers CASCADE;")
            cur.execute("DROP TABLE IF EXISTS laporan_submissions CASCADE;")
            cur.execute("DROP TABLE IF EXISTS laporan_form_fields CASCADE;")
            cur.execute("DROP TABLE IF EXISTS laporan_form_targets CASCADE;")
            cur.execute("DROP TABLE IF EXISTS laporan_forms CASCADE;")
        print("✓ Tabel laporan lama berhasil dihapus.")
    except Exception as e:
        print(f"✗ Gagal menghapus tabel: {e}")
        sys.exit(1)
        
    # Ambil konfigurasi DB dari .env
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    
    if not db_name or not db_user:
        print("Error: Konfigurasi database tidak ditemukan di .env.")
        sys.exit(1)
        
    print(f"2. Memulihkan (pg_restore) tabel laporan ke database '{db_name}'...")
    env = os.environ.copy()
    if db_pass:
        env["PGPASSWORD"] = db_pass
        
    cmd = [
        "pg_restore",
        "-h", db_host,
        "-p", db_port,
        "-U", db_user,
        "-d", db_name,
        "-t", "laporan_forms",
        "-t", "laporan_form_targets",
        "-t", "laporan_form_fields",
        "-t", "laporan_submissions",
        "-t", "laporan_submission_answers",
        "-t", "laporan_submission_files",
        backup_file
    ]
    
    try:
        subprocess.run(cmd, env=env, check=True)
        print("✓ Pemulihan database selesai dengan sukses!")
    except subprocess.CalledProcessError as e:
        print(f"✗ pg_restore gagal dengan error: {e}")
        sys.exit(1)
    except FileNotFoundError:
        # Fallback to absolute PostgreSQL path if pg_restore is not in PATH (especially for macOS local environment)
        fallback_paths = [
            "/usr/bin/pg_restore",
            "/usr/local/bin/pg_restore",
            "/Library/PostgreSQL/18/bin/pg_restore",
            "/Library/PostgreSQL/17/bin/pg_restore",
            "/Library/PostgreSQL/16/bin/pg_restore",
            "/Library/PostgreSQL/15/bin/pg_restore",
        ]
        restored = False
        for path in fallback_paths:
            if os.path.exists(path):
                cmd[0] = path
                try:
                    subprocess.run(cmd, env=env, check=True)
                    print(f"✓ Pemulihan database selesai dengan sukses (menggunakan {path})!")
                    restored = True
                    break
                except subprocess.CalledProcessError as err:
                    print(f"✗ Gagal menjalankan {path}: {err}")
                    sys.exit(1)
        if not restored:
            print("Error: Command 'pg_restore' tidak ditemukan. Pastikan postgresql-client terpasang di server.")
            sys.exit(1)
    finally:
        shutdown_pool()

if __name__ == "__main__":
    main()
