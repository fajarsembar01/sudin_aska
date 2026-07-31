import psycopg2
from werkzeug.security import generate_password_hash

conn = psycopg2.connect(
    dbname="aska_sudin",
    user="postgres",
    password="sembar03",
    host="127.0.0.1",
    port="5432",
)
cur = conn.cursor()
cur.execute(
    "SELECT id, email, full_name, role, school_id FROM dashboard_users WHERE email = 'tunasbangsasembar@gmail.com'"
)
user = cur.fetchone()
print("Selected user:", user)

if user:
    # Reset password to password123
    new_hash = generate_password_hash(
        "password123", method="pbkdf2:sha256", salt_length=12
    )
    cur.execute(
        "UPDATE dashboard_users SET password_hash = %s WHERE id = %s",
        (new_hash, user[0]),
    )
    conn.commit()
    print("Password for tunasbangsasembar@gmail.com updated to password123")

cur.close()
conn.close()
