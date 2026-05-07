import os
import sys

# Tambahkan root proyek ke sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from dashboard.db_access import get_cursor

def run_migrations():
    # File-file SQL migrasi yang belum terpasang
    migration_files = [
        "dashboard/migrations/021_add_reopen_requests.sql",
        "dashboard/migrations/026_add_hospitality.sql",
        "dashboard/migrations/027_seed_hospitality_proses_pelayanan.sql",
        "dashboard/migrations/028_add_hospitality_guestbook_reviews.sql",
        "dashboard/migrations/029_add_hospitality_soft_delete.sql",
        "dashboard/migrations/030_add_hospitality_preview_access.sql",
        "dashboard/migrations/031_add_hospitality_activity_logs.sql",
        "dashboard/migrations/032_add_cms_artikel.sql",
        "dashboard/migrations/033_add_hospitality_guestbook_extra_questions.sql",
    ]
    
    print("Mengeksekusi migrasi modul tambahan (Hospitality & Reopen)...")
    try:
        with get_cursor(commit=True) as cur:
            for file_path in migration_files:
                full_path = os.path.join(PROJECT_ROOT, file_path)
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8") as f:
                        sql_content = f.read()
                        print(f" -> Sedang memproses: {file_path}")
                        cur.execute(sql_content)
                else:
                    print(f" -> LEWATKAN (file tidak ada): {file_path}")
        print("Migrasi Sukses! Struktur tabel hospitality_reopen_requests dkk sudah siap.")
    except Exception as e:
        print(f"Gagal saat migrasi: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_migrations()
