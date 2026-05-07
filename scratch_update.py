import psycopg2
import random
import datetime
from datetime import timedelta

conn = psycopg2.connect(dbname='sudin_aska', user='postgres', password='Jajangme0ng', host='localhost', port='5432')
cur = conn.cursor()
cur.execute('SELECT id FROM hospitality_guestbook_reviews')
ids = [row[0] for row in cur.fetchall()]

start_date = datetime.date(2026, 2, 18)
end_date = datetime.date(2026, 4, 24)
excluded_dates = [
    datetime.date(2026, 3, 18),
    datetime.date(2026, 3, 19),
    datetime.date(2026, 3, 20),
    datetime.date(2026, 3, 23),
    datetime.date(2026, 3, 24),
    datetime.date(2026, 3, 30),
    datetime.date(2026, 4, 3)
]

dates = []
curr = start_date
while curr <= end_date:
    if curr.weekday() < 5 and curr not in excluded_dates:
        dates.append(curr)
    curr += timedelta(days=1)

updates = []
for i in ids:
    d = random.choice(dates)
    h = random.randint(7, 16)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    updates.append(f"UPDATE hospitality_guestbook_reviews SET tanggal_edit = '{d} {h:02d}:{m:02d}:{s:02d}+0700' WHERE id = {i};")

with open('update_tanggal_edit.sql', 'w') as f:
    f.write('-- Script SQL untuk menambahkan dan mengupdate kolom tanggal_edit\n\n')
    f.write('-- 1. Tambahkan kolom tanggal_edit jika belum ada\n')
    f.write('ALTER TABLE hospitality_guestbook_reviews ADD COLUMN IF NOT EXISTS tanggal_edit TIMESTAMPTZ;\n\n')
    f.write('-- 2. Update data kolom sesuai dengan data DB saat ini\n')
    f.write('\n'.join(updates))

cur.close()
conn.close()
print('Done')
