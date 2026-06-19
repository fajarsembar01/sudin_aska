import os
import sys

# Add project root to path to import db modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from dashboard.db_access import get_cursor, shutdown_pool

def main():
    print("Membuat ulang Primary Key dan Foreign Key pada tabel laporan...")
    with get_cursor(commit=True) as cur:
        # Recreate Primary Keys
        pks = [
            ("laporan_forms", "laporan_forms_pkey", "PRIMARY KEY (id)"),
            ("laporan_form_fields", "laporan_form_fields_pkey", "PRIMARY KEY (id)"),
            ("laporan_submissions", "laporan_submissions_pkey", "PRIMARY KEY (id)"),
            ("laporan_submission_answers", "laporan_submission_answers_pkey", "PRIMARY KEY (id)"),
            ("laporan_submission_files", "laporan_submission_files_pkey", "PRIMARY KEY (id)"),
        ]
        for table, name, definition in pks:
            try:
                cur.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} {definition}")
                print(f"✓ Added PK {name} to {table}")
            except Exception as e:
                print(f"⚠ Skipped PK {name}: {e}")
                
        # Recreate Foreign Keys
        fks = [
            ("laporan_form_fields", "fk_laporan_fields_form", "FOREIGN KEY (form_id) REFERENCES laporan_forms(id) ON DELETE CASCADE"),
            ("laporan_submissions", "fk_laporan_submissions_form", "FOREIGN KEY (form_id) REFERENCES laporan_forms(id) ON DELETE CASCADE"),
            ("laporan_submissions", "fk_laporan_submissions_school", "FOREIGN KEY (school_id) REFERENCES portal_schools(id) ON DELETE CASCADE"),
            ("laporan_submission_answers", "fk_laporan_answers_submission", "FOREIGN KEY (submission_id) REFERENCES laporan_submissions(id) ON DELETE CASCADE"),
            ("laporan_submission_answers", "fk_laporan_answers_field", "FOREIGN KEY (field_id) REFERENCES laporan_form_fields(id) ON DELETE CASCADE"),
            ("laporan_submission_files", "fk_laporan_files_answer", "FOREIGN KEY (answer_id) REFERENCES laporan_submission_answers(id) ON DELETE CASCADE"),
        ]
        for table, name, definition in fks:
            try:
                cur.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} {definition}")
                print(f"✓ Added FK {name} to {table}")
            except Exception as e:
                print(f"⚠ Skipped FK {name}: {e}")
                
    shutdown_pool()
    print("Selesai!")

if __name__ == "__main__":
    main()
