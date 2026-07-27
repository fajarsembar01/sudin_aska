import psycopg2, os
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
cur = conn.cursor()

cur.execute("""
    SELECT a.id, a.activity_code, a.status, r.id as report_id, r.status as report_status
    FROM monev_bos_activities a
    JOIN monev_bos_reports r ON a.report_id = r.id
    WHERE a.activity_code = '01.02.26'
""")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
print("=== Activity 01.02.26 ===")
for row in rows:
    d = dict(zip(cols, row))
    print(d)
    print(f"  -> Activity status : {d['status']}")
    print(f"  -> Report status   : {d['report_status']}")
    
    if d['report_status'] not in ['draft', 'needs_revision']:
        print("  !! ALASAN: Report sudah di-submit/approved, semua edit diblokir")
    elif d['status'] == 'valid':
        print("  !! ALASAN: Kegiatan sudah divalidasi 'Sesuai', perlu Ajukan Reopen ke admin")
    elif d['status'] in ['pending', 'invalid']:
        print("  OK: Seharusnya bisa di-edit")

cur.close()
conn.close()
