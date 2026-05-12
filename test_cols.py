import sys
sys.path.append('.')
from dashboard.db_access import get_cursor
with get_cursor() as cur:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='portal_kelurahan'")
    print([r['column_name'] for r in cur.fetchall()])
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='portal_kecamatan'")
    print([r['column_name'] for r in cur.fetchall()])
