import os
from dashboard.db_access import get_cursor

def generate_sql():
    sql_statements = [
        "-- Script SQL untuk menambahkan dan mengupdate kolom tanggal_edit",
        "",
        "-- 1. Tambahkan kolom tanggal_edit jika belum ada",
        "ALTER TABLE hospitality_guestbook_reviews ADD COLUMN IF NOT EXISTS tanggal_edit TIMESTAMPTZ;",
        "",
        "-- 2. Update data kolom sesuai dengan data DB saat ini"
    ]
    
    with get_cursor() as cur:
        cur.execute("SELECT id, completed_at, created_at FROM hospitality_guestbook_reviews")
        rows = cur.fetchall()
        for row in rows:
            r_id = row['id']
            # Ambil completed_at jika ada, jika tidak gunakan created_at
            tanggal_edit = row['completed_at'] or row['created_at']
            if tanggal_edit:
                ts_str = tanggal_edit.strftime('%Y-%m-%d %H:%M:%S%z')
                sql_statements.append(f"UPDATE hospitality_guestbook_reviews SET tanggal_edit = '{ts_str}' WHERE id = {r_id};")

    output_path = os.path.join(os.getcwd(), 'update_tanggal_edit.sql')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sql_statements))
        f.write('\n')

if __name__ == '__main__':
    generate_sql()
    print("Berhasil men-generate update_tanggal_edit.sql dengan baris data lengkap.")
