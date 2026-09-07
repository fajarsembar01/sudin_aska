import psycopg2

conn = psycopg2.connect(
    dbname="sudin_aska",
    user="postgres",
    password="Jajangme0ng",
    host="localhost",
    port="5432",
)
cur = conn.cursor()
cur.execute(
    "SELECT id, tanggal_edit FROM hospitality_guestbook_reviews WHERE tanggal_edit IS NOT NULL"
)
rows = cur.fetchall()

updates = []
for r in rows:
    # Format the datetime object to string
    dt_str = r[1].strftime("%Y-%m-%d %H:%M:%S%z")
    # PostgreSQL timestamptz string format insertion
    updates.append(
        f"UPDATE hospitality_guestbook_reviews SET tanggal_edit = '{dt_str}' WHERE id = {r[0]};"
    )

with open("server_update_tanggal_edit.sql", "w") as f:
    f.write(
        "-- Script SQL untuk menambahkan dan mengupdate kolom tanggal_edit di SERVER\n\n"
    )
    f.write("-- 1. Tambahkan kolom tanggal_edit jika belum ada\n")
    f.write(
        "ALTER TABLE hospitality_guestbook_reviews ADD COLUMN IF NOT EXISTS tanggal_edit TIMESTAMPTZ;\n\n"
    )
    f.write("-- 2. Update data kolom sesuai dengan data DB lokal\n")
    f.write("\n".join(updates))

cur.close()
conn.close()
print(f"Successfully generated server_update_tanggal_edit.sql with {len(rows)} rows.")
