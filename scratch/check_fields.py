import sys

sys.path.append(".")
import json

from dashboard.app import create_app
from dashboard.db_access import get_db_connection

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.id, f.title, ff.field_key, ff.field_type, ff.options_json
        FROM laporan_forms f
        JOIN laporan_form_fields ff ON ff.form_id = f.id
        WHERE ff.field_type = 'upload_gambar'
        ORDER BY f.updated_at DESC LIMIT 5
    """)
    rows = cur.fetchall()
    for r in rows:
        print(r)
    cur.close()
    conn.close()
