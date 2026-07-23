import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from dashboard.db_access import get_cursor, shutdown_pool

def main():
    tables = [
        "laporan_forms",
        "laporan_form_fields",
        "laporan_form_targets",
        "laporan_submissions",
        "laporan_submission_answers",
        "laporan_submission_files",
    ]
    
    print("Memulai perbaikan sequence auto-increment untuk tabel laporan...")
    with get_cursor(commit=True) as cur:
        for table in tables:
            seq_name = f"{table}_id_seq"
            
            # 1. Buat sequence jika belum ada
            cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")
            
            # 2. Set default value nextval pada kolom id
            cur.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('{seq_name}')")
            
            # 3. Sinkronkan nilai sequence dengan MAX(id) saat ini
            cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
            max_id = cur.fetchone()[0]
            next_val = max(1, max_id + 1)
            
            cur.execute(f"SELECT setval('{seq_name}', %s, false)", (next_val,))
            print(f"✓ Berhasil mengaitkan {seq_name} ke {table}.id (nilai berikutnya: {next_val})")

if __name__ == "__main__":
    main()
    shutdown_pool()
